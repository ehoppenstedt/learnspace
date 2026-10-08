"""In-app credit: an append-only ledger in MXN centavos.

Credits are how App Store purchases are refunded (Apple alone can refund those, and only in
full), and they pay for any booking on any device. Spending locks the user's ledger rows so two
checkouts can't spend the same balance.
"""

from django.db import transaction
from django.db.models import Sum

from apps.payments.models import CreditEntry


def balance(user) -> int:
    return CreditEntry.objects.filter(user=user).aggregate(n=Sum("amount_cents"))["n"] or 0


def _lock(user) -> None:
    from apps.accounts.models import User

    User.objects.select_for_update().filter(pk=user.pk).first()


def grant(user, amount_cents: int, *, kind: str, key: str, booking=None, refund=None, note="", created_by=None) -> CreditEntry:
    if amount_cents <= 0:
        raise ValueError("credit grant must be positive")
    entry, _ = CreditEntry.objects.get_or_create(idempotency_key=key, defaults={
        "user": user, "amount_cents": amount_cents, "kind": kind, "booking": booking, "refund": refund, "note": note,
        "created_by": created_by})
    return entry


def spend(user, amount_cents: int, *, booking, key: str) -> CreditEntry | None:
    """Must run inside the caller's transaction."""
    if amount_cents <= 0:
        return None
    assert transaction.get_connection().in_atomic_block
    _lock(user)
    if balance(user) < amount_cents:
        raise ValueError("insufficient credit")
    entry, _ = CreditEntry.objects.get_or_create(idempotency_key=key, defaults={
        "user": user, "amount_cents": -amount_cents, "kind": CreditEntry.Kind.SPEND, "booking": booking})
    return entry


def spendable(user) -> int:
    _lock(user)
    return max(balance(user), 0)
