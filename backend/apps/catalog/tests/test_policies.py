import pytest

from apps.catalog.models import CancellationPolicy
from apps.catalog.policies import RuleSpec, validate_rules

STANDARD = [
    RuleSpec("learner_cancel", 24, None, 100, True),
    RuleSpec("learner_cancel", 0, 24, 50, False),
    RuleSpec("no_show", 0, None, 0, False),
]


def test_standard_is_valid():
    assert validate_rules(STANDARD) == []


@pytest.mark.django_db
def test_seeded_standard_policy_matches_spec():
    policy = CancellationPolicy.objects.get(code="standard")
    rules = [RuleSpec(r.applies_to, r.min_hours_before, r.max_hours_before, r.listed_refund_pct, r.refund_fee)
             for r in policy.rules.all()]
    assert sorted(rules, key=lambda r: (r.applies_to, r.min_hours_before)) == sorted(STANDARD, key=lambda r: (r.applies_to, r.min_hours_before))
    assert policy.is_default


def test_new_tier_is_config_only():
    flexible = [
        RuleSpec("learner_cancel", 2, None, 100, True),
        RuleSpec("learner_cancel", 0, 2, 0, False),
        RuleSpec("no_show", 0, None, 0, False),
    ]
    assert validate_rules(flexible) == []


@pytest.mark.parametrize("rules", [
    [RuleSpec("learner_cancel", 24, None, 100, True), RuleSpec("no_show", 0, None, 0, False)],          # gap at 0-24
    [RuleSpec("learner_cancel", 0, 30, 50, False), RuleSpec("learner_cancel", 24, None, 100, True),
     RuleSpec("no_show", 0, None, 0, False)],                                                          # overlap
    [RuleSpec("learner_cancel", 0, 24, 50, False), RuleSpec("no_show", 0, None, 0, False)],            # not open-ended
    [RuleSpec("learner_cancel", 0, None, 100, True)],                                                   # no no-show
    [RuleSpec("learner_cancel", 0, None, 50, True), RuleSpec("no_show", 0, None, 0, False)],           # fee w/ partial
])
def test_invalid_policies(rules):
    assert validate_rules(rules)
