from django.conf import settings
from django.core.mail import send_mail
from django.utils import translation
from django.utils.translation import gettext as _

from apps.catalog.models import Experience


def send_decision_email(experience_id: str, decision: str) -> None:
    experience = Experience.objects.select_related("provider__user").get(pk=experience_id)
    user = experience.provider.user
    if not user.email:
        return
    revision = experience.revisions.filter(decided_at__isnull=False).order_by("-decided_at").first()
    with translation.override(user.ui_language or "es"):
        subjects = {
            "approved": _("Tu experiencia fue aprobada"),
            "changes_requested": _("Tu experiencia necesita cambios"),
            "rejected": _("Tu experiencia no fue aprobada"),
        }
        lines = [
            _("Hola %(name)s,") % {"name": user.first_name or experience.provider.display_name},
            "",
            f"«{experience.title}»: {subjects.get(decision, decision)}.",
        ]
        if revision and revision.reviewer_note and decision != "approved":
            lines += ["", _("Comentarios del equipo:"), revision.reviewer_note]
        lines += ["", f"— {settings.BRAND_NAME}"]
        send_mail(subjects.get(decision, decision), "\n".join(lines), None, [user.email])
