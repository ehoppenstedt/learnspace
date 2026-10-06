from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import ProviderProfile, ProviderVerification
from apps.catalog import services
from apps.catalog.models import Experience, ExperienceRevision
from apps.moderation.models import AdminAction
from conftest import make_live_experience, ready_image

pytestmark = pytest.mark.django_db


@pytest.fixture
def pending(provider_user):
    experience = make_live_experience(provider_user)
    Experience.objects.filter(pk=experience.pk).update(status="draft")
    experience.refresh_from_db()
    services.submit(experience)
    return experience.revisions.get(review_status="pending")


def test_queue_defaults_to_pending_and_renders_decision_page(client, admin_user, pending):
    client.force_login(admin_user)
    res = client.get("/admin/catalog/experiencerevision/")
    assert res.status_code == 302 and "review_status__exact=pending" in res["Location"]
    res = client.get(res["Location"])
    assert res.status_code == 200 and pending.experience.title in res.content.decode()
    page = client.get(f"/admin/catalog/experiencerevision/{pending.pk}/change/")
    body = page.content.decode()
    assert page.status_code == 200
    assert "$550.00 MXN" in body  # total incl. 10% fee shown to the reviewer
    assert "Submit decision" in body


def test_approve_through_admin(client, admin_user, pending):
    client.force_login(admin_user)
    res = client.post(f"/admin/catalog/experiencerevision/{pending.pk}/change/", {"decision": "approve", "note": ""})
    assert res.status_code == 302
    pending.refresh_from_db()
    assert pending.review_status == "approved"
    assert Experience.objects.get(pk=pending.experience_id).status == "live"


def test_request_changes_requires_reason_and_note(client, admin_user, pending):
    client.force_login(admin_user)
    res = client.post(f"/admin/catalog/experiencerevision/{pending.pk}/change/", {"decision": "request_changes"})
    assert res.status_code == 200  # stays on page with an error
    assert ExperienceRevision.objects.get(pk=pending.pk).review_status == "pending"
    client.post(f"/admin/catalog/experiencerevision/{pending.pk}/change/",
                {"decision": "request_changes", "reason_code": "low_quality_media", "note": "Fotos más nítidas, por favor."})
    assert ExperienceRevision.objects.get(pk=pending.pk).review_status == "changes_requested"
    assert Experience.objects.get(pk=pending.experience_id).status == "changes_requested"


def test_verification_queue(client, admin_user, provider_user):
    ProviderProfile.objects.filter(pk=provider_user.pk).update(verification_status="pending")
    media = ready_image(provider_user)
    media.kind, media.external_url = "document", ""
    media.save()
    doc = ProviderVerification.objects.create(provider=provider_user.provider_profile, doc_type="government_id", media=media)
    client.force_login(admin_user)
    assert client.get(f"/admin/accounts/providerverification/{doc.pk}/change/").status_code == 200
    assert AdminAction.objects.filter(action="provider.view_doc").exists()  # document views are audited
    client.post(f"/admin/accounts/providerverification/{doc.pk}/change/", {"decision": "reject", "reason_code": "id_unreadable"})
    assert ProviderProfile.objects.get(pk=provider_user.pk).verification_status == "rejected"


def test_fee_change_is_audited_and_rows_are_immutable(client, admin_user):
    client.force_login(admin_user)
    when = (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%d")
    res = client.post("/admin/payments/feeconfig/add/", {
        "fee_bps": 1200, "effective_from_0": when, "effective_from_1": "00:00:00", "note": "test"})
    assert res.status_code == 302, res.content.decode()[:500]
    action = AdminAction.objects.get(action="config.create", target_type="payments.feeconfig")
    assert action.after["fee_bps"] == 1200
    from apps.payments.models import FeeConfig

    row = FeeConfig.objects.get(fee_bps=1200)
    assert client.get(f"/admin/payments/feeconfig/{row.pk}/change/").status_code in (200, 403)
    res = client.post(f"/admin/payments/feeconfig/{row.pk}/change/", {"fee_bps": 1, "effective_from_0": when, "effective_from_1": "00:00:00"})
    assert FeeConfig.objects.get(pk=row.pk).fee_bps == 1200


def test_policy_admin_rejects_gaps(client, admin_user):
    client.force_login(admin_user)
    data = {
        "code": "firm", "name_es": "Firme", "name_en": "Firm", "is_active": "on",
        "rules-TOTAL_FORMS": "2", "rules-INITIAL_FORMS": "0", "rules-MIN_NUM_FORMS": "0", "rules-MAX_NUM_FORMS": "1000",
        "rules-0-applies_to": "learner_cancel", "rules-0-min_hours_before": "72", "rules-0-listed_refund_pct": "100", "rules-0-refund_fee": "on",
        "rules-1-applies_to": "no_show", "rules-1-min_hours_before": "0", "rules-1-listed_refund_pct": "0",
    }
    res = client.post("/admin/catalog/cancellationpolicy/add/", data)
    assert res.status_code == 200 and "must start at 0 hours" in res.content.decode()
    data.update({"rules-TOTAL_FORMS": "3", "rules-2-applies_to": "learner_cancel", "rules-2-min_hours_before": "0",
                 "rules-2-max_hours_before": "72", "rules-2-listed_refund_pct": "0"})
    res = client.post("/admin/catalog/cancellationpolicy/add/", data)
    assert res.status_code == 302
    assert AdminAction.objects.filter(action="config.policy_rules").exists()
