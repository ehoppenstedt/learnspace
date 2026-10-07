"""Cancellation policy validation. Policies are data; this keeps that data coherent."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleSpec:
    applies_to: str
    min_hours_before: int
    max_hours_before: int | None
    listed_refund_pct: int
    refund_fee: bool


def validate_rules(rules: list[RuleSpec]) -> list[str]:
    """Learner-cancel rules must tile [0h, ∞) with no gaps or overlaps; exactly one no-show rule."""
    errors = []
    cancel = sorted((r for r in rules if r.applies_to == "learner_cancel"), key=lambda r: r.min_hours_before)
    if not cancel:
        errors.append("At least one learner_cancel rule is required.")
    else:
        if cancel[0].min_hours_before != 0:
            errors.append("learner_cancel rules must start at 0 hours.")
        for prev, nxt in zip(cancel, cancel[1:], strict=False):
            if prev.max_hours_before is None:
                errors.append("Only the last learner_cancel rule may be open-ended.")
            elif prev.max_hours_before != nxt.min_hours_before:
                errors.append(f"Gap or overlap between {prev.max_hours_before}h and {nxt.min_hours_before}h.")
        if cancel[-1].max_hours_before is not None:
            errors.append("The last learner_cancel rule must be open-ended (no max).")
    no_show = [r for r in rules if r.applies_to == "no_show"]
    if len(no_show) != 1:
        errors.append("Exactly one no_show rule is required.")
    for r in rules:
        if not 0 <= r.listed_refund_pct <= 100:
            errors.append("Refund percentage must be between 0 and 100.")
        if r.refund_fee and r.listed_refund_pct != 100:
            errors.append("The service fee can only be refunded together with a 100% refund.")
    return errors
