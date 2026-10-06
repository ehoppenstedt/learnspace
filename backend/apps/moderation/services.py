"""Every admin decision goes through here so it is always written to the audit log."""

from django.db import transaction
from django.forms.models import model_to_dict
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import status

from apps.accounts.models import ProviderProfile, ProviderVerification
from apps.catalog import services as catalog
from apps.catalog.models import Experience, ExperienceRevision
from apps.core.exceptions import DomainError
from apps.moderation.models import AdminAction, ReasonCode


def _jsonable(data: dict) -> dict:
    out = {}
    for key, value in data.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, (list, tuple)):
            out[key] = [str(v) if not isinstance(v, (str, int, float, bool)) else v for v in value]
        else:
            out[key] = str(value)
    return out


def snapshot_model(instance, exclude=()) -> dict:
    return _jsonable(model_to_dict(instance, exclude=list(exclude)))


def log(admin, action: str, target, *, reason_code: str = "", note: str = "", before=None, after=None) -> AdminAction:
    return AdminAction.objects.create(
        admin=admin, action=action, target_type=target._meta.label_lower, target_id=str(target.pk),
        reason_code=reason_code, note=note, before=before or {}, after=after or {},
    )


def _notify(experience: Experience, decision: str) -> None:
    from apps.moderation.tasks import send_decision_email_task

    transaction.on_commit(
        lambda: send_decision_email_task.defer(experience_id=str(experience.pk), decision=decision)
    )


def _lock_pending(revision: ExperienceRevision) -> ExperienceRevision:
    revision = ExperienceRevision.objects.select_for_update().select_related("experience__provider").get(pk=revision.pk)
    if revision.review_status != ExperienceRevision.ReviewStatus.PENDING:
        raise DomainError("not_pending", _("Esta revisión ya fue decidida."))
    return revision


def approve(admin, revision: ExperienceRevision, note: str = "") -> ExperienceRevision:
    with transaction.atomic():
        revision = _lock_pending(revision)
        experience = Experience.objects.select_for_update().get(pk=revision.experience_id)
        before = catalog.snapshot(experience) | {"status": experience.status}
        if revision.kind == ExperienceRevision.Kind.INITIAL:
            from apps.payments.services import provider_ready_for_payouts

            ready, missing = provider_ready_for_payouts(experience.provider)
            if not ready:
                code = "provider_not_verified" if "identity" in missing else "provider_payments_incomplete"
                raise DomainError(code, _("El proveedor aún no completa: %(m)s.") % {"m": ", ".join(missing)},
                                  status.HTTP_400_BAD_REQUEST, fields={"missing": missing})
            experience.status = Experience.Status.LIVE
            experience.published_at = experience.published_at or timezone.now()
            experience.save(update_fields=["status", "published_at", "updated_at"])
        else:
            catalog.apply_payload(experience, revision.payload)
        catalog.refresh_denorm(experience)
        revision.review_status = ExperienceRevision.ReviewStatus.APPROVED
        revision.decided_at, revision.decided_by = timezone.now(), admin
        revision.reason_code, revision.reviewer_note = ReasonCode.APPROVED, note
        revision.save()
        log(admin, "experience.approve", experience, reason_code=ReasonCode.APPROVED, note=note, before=before,
            after=catalog.snapshot(experience) | {"status": experience.status, "revision": revision.number})
        _notify(experience, "approved")
    return revision


def request_changes(admin, revision: ExperienceRevision, reason_code: str, note: str) -> ExperienceRevision:
    return _decline(admin, revision, reason_code, note, ExperienceRevision.ReviewStatus.CHANGES_REQUESTED)


def reject(admin, revision: ExperienceRevision, reason_code: str, note: str) -> ExperienceRevision:
    return _decline(admin, revision, reason_code, note, ExperienceRevision.ReviewStatus.REJECTED)


def _decline(admin, revision, reason_code, note, outcome) -> ExperienceRevision:
    if reason_code not in ReasonCode.values or reason_code == ReasonCode.APPROVED:
        raise DomainError("invalid_reason", _("Elige un motivo."), status.HTTP_400_BAD_REQUEST)
    if not note.strip():
        raise DomainError("note_required", _("Explica al proveedor qué cambiar."), status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        revision = _lock_pending(revision)
        experience = Experience.objects.select_for_update().get(pk=revision.experience_id)
        before_status = experience.status
        if revision.kind == ExperienceRevision.Kind.INITIAL:
            experience.status = (
                Experience.Status.CHANGES_REQUESTED
                if outcome == ExperienceRevision.ReviewStatus.CHANGES_REQUESTED
                else Experience.Status.REJECTED
            )
            experience.save(update_fields=["status", "updated_at"])
        # For edits of a live experience, the live version is untouched.
        revision.review_status = outcome
        revision.decided_at, revision.decided_by = timezone.now(), admin
        revision.reason_code, revision.reviewer_note = reason_code, note
        revision.save()
        action = "experience.request_changes" if outcome == ExperienceRevision.ReviewStatus.CHANGES_REQUESTED else "experience.reject"
        log(admin, action, experience, reason_code=reason_code, note=note,
            before={"status": before_status}, after={"status": experience.status, "revision": revision.number})
        _notify(experience, outcome)
    return revision


def decide_verification(admin, doc: ProviderVerification, *, approve_doc: bool, reason_code: str = "", note: str = "") -> ProviderVerification:
    if not approve_doc and (reason_code not in ReasonCode.values or reason_code == ReasonCode.APPROVED):
        raise DomainError("invalid_reason", _("Elige un motivo."), status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        doc = ProviderVerification.objects.select_for_update().select_related("provider").get(pk=doc.pk)
        if doc.status != ProviderVerification.Status.PENDING:
            raise DomainError("not_pending", _("Este documento ya fue revisado."))
        provider = ProviderProfile.objects.select_for_update().get(pk=doc.provider_id)
        before = {"doc": doc.status, "provider": provider.verification_status}
        doc.status = ProviderVerification.Status.APPROVED if approve_doc else ProviderVerification.Status.REJECTED
        doc.reviewed_by, doc.reviewed_at = admin, timezone.now()
        doc.reason_code, doc.notes = (ReasonCode.APPROVED if approve_doc else reason_code), note
        doc.save()
        if doc.doc_type == ProviderVerification.DocType.GOVERNMENT_ID:
            if approve_doc:
                provider.verification_status = ProviderProfile.Verification.VERIFIED
            elif not provider.verifications.filter(doc_type=doc.doc_type, status=ProviderVerification.Status.APPROVED).exists():
                provider.verification_status = ProviderProfile.Verification.REJECTED
            provider.save(update_fields=["verification_status"])
        log(admin, "provider.verify_doc" if approve_doc else "provider.reject_doc", provider,
            reason_code=doc.reason_code, note=note, before=before,
            after={"doc": doc.status, "provider": provider.verification_status, "doc_id": str(doc.pk), "doc_type": doc.doc_type})
    return doc
