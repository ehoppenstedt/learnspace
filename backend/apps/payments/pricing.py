"""Price math. Integer centavos only. The single source of truth for fees.

fee   = round_half_up(listed_total * fee_bps / 10_000)
total = listed_total + fee

The same formula is expressed in SQL by `total_cents_expression` so the feed can filter and
sort on the total price; tests assert both agree.
"""

from dataclasses import dataclass

from django.conf import settings
from django.db.models import BigIntegerField, ExpressionWrapper, F, Value
from django.utils import timezone

BPS_DENOMINATOR = 10_000


@dataclass(frozen=True)
class PriceBreakdown:
    listed_cents: int
    fee_cents: int
    total_cents: int
    fee_bps: int
    seats: int = 1

    def as_dict(self) -> dict:
        return {
            "listed_cents": self.listed_cents,
            "fee_cents": self.fee_cents,
            "total_cents": self.total_cents,
            "currency": "MXN",
        }


def fee_for(listed_cents: int, fee_bps: int) -> int:
    if listed_cents < 0 or fee_bps < 0:
        raise ValueError("Amounts and fee must be non-negative")
    # Round half up on exact integers: no floats anywhere.
    return (listed_cents * fee_bps + BPS_DENOMINATOR // 2) // BPS_DENOMINATOR


def price(listed_cents_per_seat: int, fee_bps: int, seats: int = 1) -> PriceBreakdown:
    """Fee is computed once on the whole line, not per seat, to avoid compounding rounding."""
    if seats < 1:
        raise ValueError("seats must be >= 1")
    listed = listed_cents_per_seat * seats
    fee = fee_for(listed, fee_bps)
    return PriceBreakdown(listed_cents=listed, fee_cents=fee, total_cents=listed + fee, fee_bps=fee_bps, seats=seats)


def current_fee_bps(at=None) -> int:
    from apps.payments.models import FeeConfig

    at = at or timezone.now()
    row = FeeConfig.objects.filter(effective_from__lte=at).order_by("-effective_from").values_list("fee_bps", flat=True).first()
    return settings.DEFAULT_FEE_BPS if row is None else row


def total_cents_expression(fee_bps: int, field: str = "listed_price_cents"):
    """SQL equivalent of price(...).total_cents for one seat. Integer division truncates
    in Postgres, which equals floor for non-negative values, so +5000 then // 10000 is
    round-half-up exactly like fee_for()."""
    return ExpressionWrapper(
        F(field) + (F(field) * Value(fee_bps) + Value(BPS_DENOMINATOR // 2)) / Value(BPS_DENOMINATOR),
        output_field=BigIntegerField(),
    )


# ---------------------------------------------------------------------------
# App Store price (group online classes bought in the iOS app)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StorePrice:
    total_cents: int  # what the learner pays Apple (an App Store price point)
    surcharge_cents: int  # total - (listed + fee): covers Apple's commission and the VAT Apple remits
    product_id: str


def store_required_cents(listed_cents: int, fee_cents: int) -> int:
    """Smallest customer price that, after Apple remits VAT and keeps its commission, leaves the
    platform what a card sale would: the listed price for the provider plus the fee net of VAT.

        net = price / (1 + vat) * (1 - commission)  >=  listed + fee / (1 + vat)
    """
    vat, commission = settings.APP_STORE_VAT_BPS, settings.APP_STORE_COMMISSION_BPS
    numerator = listed_cents * (BPS_DENOMINATOR + vat) + fee_cents * BPS_DENOMINATOR
    denominator = BPS_DENOMINATOR - commission
    return -(-numerator // denominator)  # ceil, integers only


def product_id_for(points_pesos: int) -> str:
    return f"{settings.APPLE_BUNDLE_ID}.class.mxn{points_pesos}"


def store_price(listed_cents: int, fee_cents: int) -> StorePrice | None:
    """None when the class is more expensive than the highest configured price point."""
    required = store_required_cents(listed_cents, fee_cents)
    for pesos in sorted(settings.IAP_PRICE_POINTS_MXN):
        if pesos * 100 >= required:
            total = pesos * 100
            return StorePrice(total, total - listed_cents - fee_cents, product_id_for(pesos))
    return None


def store_point_at_most(cents: int) -> int | None:
    """Largest price point <= cents (used when credits pay part of an App Store purchase)."""
    points = [p * 100 for p in settings.IAP_PRICE_POINTS_MXN if p * 100 <= cents]
    return max(points) if points else None


def store_point_at_least(cents: int) -> int | None:
    points = [p * 100 for p in settings.IAP_PRICE_POINTS_MXN if p * 100 >= cents]
    return min(points) if points else None
