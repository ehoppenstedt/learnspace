from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import Experience
from apps.payments.models import FeeConfig
from apps.payments.pricing import current_fee_bps, fee_for, price, total_cents_expression
from conftest import make_live_experience


class TestFeeFor:
    @pytest.mark.parametrize(
        ("listed", "bps", "expected"),
        [
            (50000, 500, 2500),     # $500.00 at 5% -> $25.00
            (19900, 500, 995),      # $199.00 -> $9.95
            (10, 500, 1),           # 0.5 centavo rounds half up
            (9, 500, 0),            # 0.45 centavo rounds down
            (30, 500, 2),           # 1.5 -> 2
            (12345, 1250, 1543),    # 1543.125 -> 1543
            (12348, 1250, 1544),    # 1543.5 -> 1544 (half up)
            (0, 500, 0),
            (9_999_999, 500, 500_000),  # 499999.95 -> 500000
        ],
    )
    def test_round_half_up_integer_math(self, listed, bps, expected):
        assert fee_for(listed, bps) == expected

    def test_zero_fee(self):
        assert fee_for(50000, 0) == 0

    def test_rejects_negative(self):
        with pytest.raises(ValueError):
            fee_for(-1, 500)


class TestPrice:
    def test_breakdown_sums(self):
        p = price(50000, 500)
        assert (p.listed_cents, p.fee_cents, p.total_cents) == (50000, 2500, 52500)

    def test_fee_computed_once_on_line_total(self):
        # Per-seat rounding would give 3 * round(0.5) = 3; on the line it's round(1.5) = 2.
        p = price(10, 500, seats=3)
        assert p.listed_cents == 30
        assert p.fee_cents == 2
        assert p.total_cents == 32

    def test_seats_must_be_positive(self):
        with pytest.raises(ValueError):
            price(1000, 500, seats=0)

    def test_as_dict_has_currency(self):
        assert price(100, 500).as_dict()["currency"] == "MXN"


@pytest.mark.django_db
class TestFeeConfig:
    def test_migration_seeds_five_percent(self):
        assert current_fee_bps() == 500

    def test_latest_effective_row_wins_and_future_rows_are_ignored(self):
        FeeConfig.objects.create(fee_bps=700, effective_from=timezone.now())
        FeeConfig.objects.create(fee_bps=900, effective_from=timezone.now() + timedelta(days=1))
        assert current_fee_bps() == 700
        assert current_fee_bps(at=timezone.now() + timedelta(days=2)) == 900

    def test_default_when_table_empty(self, settings):
        FeeConfig.objects.all().delete()
        settings.DEFAULT_FEE_BPS = 450
        assert current_fee_bps() == 450


@pytest.mark.django_db
def test_sql_total_matches_python_for_many_prices(provider_user):
    """The feed filters on a SQL-computed total; it must equal the checkout total exactly."""
    exp = make_live_experience(provider_user)
    prices = [1, 9, 10, 11, 29, 30, 31, 999, 1_005, 19_990, 49_999, 50_000, 123_457, 9_999_999]
    for bps in (0, 333, 500, 750, 1250, 1500):
        for listed in prices:
            Experience.objects.filter(pk=exp.pk).update(listed_price_cents=listed)
            sql_total = Experience.objects.filter(pk=exp.pk).annotate(t=total_cents_expression(bps)).values_list("t", flat=True).get()
            assert sql_total == price(listed, bps).total_cents, (listed, bps)
