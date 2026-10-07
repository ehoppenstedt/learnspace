"""Payment receipts and provider statements behind a swappable backend.

Today: DummyReceiptBackend renders a clear, printable HTML document marked "not a CFDI".
Later: a PAC adapter (e.g. Facturapi) implements the same two methods and returns the stamped
CFDI (fee invoice for learners, retention certificate for providers). Nothing else changes.
"""

from datetime import date
from html import escape

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone
from django.utils.module_loading import import_string

STATUS_ES = {
    "pending_payment": "Pago pendiente", "pending_approval": "Esperando aprobación", "confirmed": "Confirmada",
    "declined": "No aprobada", "payment_failed": "Pago no completado", "cancelled": "Cancelada", "completed": "Completada",
    "no_show": "Inasistencia", "scheduled": "Programado", "on_hold": "En revisión", "sent": "Enviado", "reversed": "Revertido",
}


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f} MXN"


class ReceiptBackend:
    def booking_receipt(self, booking) -> tuple[str, str]:
        """(content_type, body)"""
        raise NotImplementedError

    def provider_statement(self, provider, month: date) -> tuple[str, str]:
        raise NotImplementedError


_STYLE = """
body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:24px auto;padding:0 16px;color:#1f1f1f}
h1{font-size:22px;margin:0 0 4px} .muted{color:#6a6a6a;font-size:14px}
table{width:100%;border-collapse:collapse;margin:16px 0} td,th{padding:8px 4px;border-bottom:1px solid #eee;text-align:left}
td.n,th.n{text-align:right} tr.total td{font-weight:700;border-top:2px solid #1f1f1f}
.banner{background:#fff4d6;color:#8a5a00;padding:10px 12px;border-radius:8px;font-size:14px;margin:12px 0}
"""


class DummyReceiptBackend(ReceiptBackend):
    def _page(self, title: str, body: str) -> str:
        banner = ("Documento informativo, <b>no es un comprobante fiscal (CFDI)</b>. "
                  "La facturación electrónica se habilitará antes del lanzamiento.")
        if settings.PAYMENTS_TEST_MODE:
            banner += " <b>Modo de prueba: no se realizó ningún cobro real.</b>"
        return (f"<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
                f"<title>{escape(title)}</title><style>{_STYLE}</style></head><body>"
                f"<p class='muted'>{escape(settings.BRAND_NAME)} · {escape(settings.LEGAL_ENTITY_NAME)} · RFC {escape(settings.LEGAL_RFC)}</p>"
                f"<h1>{escape(title)}</h1><div class='banner'>{banner}</div>{body}</body></html>")

    def booking_receipt(self, booking):
        refunds = sum(r.total_refund_cents for p in booking.payments.all() for r in p.refunds.all())
        sessions = "".join(
            f"<li>{timezone.localtime(bs.session.starts_at):%d/%m/%Y %H:%M}</li>"
            for bs in booking.booking_sessions.select_related("session").order_by("session__starts_at")
        )
        rows = [
            (f"{escape(booking.experience.title)} × {booking.seats}", booking.listed_cents),
            (f"Tarifa de servicio ({booking.fee_bps_snapshot / 100:.0f}%, IVA incluido)", booking.fee_cents),
        ]
        table = "".join(f"<tr><td>{label}</td><td class='n'>{_money(v)}</td></tr>" for label, v in rows)
        table += f"<tr class='total'><td>Total pagado</td><td class='n'>{_money(booking.total_cents)}</td></tr>"
        if refunds:
            table += f"<tr><td>Reembolsado</td><td class='n'>− {_money(refunds)}</td></tr>"
        payment = booking.payments.order_by("-created_at").first()
        body = (f"<p class='muted'>Reserva {booking.code} · {escape(booking.learner.full_name)} · "
                f"{timezone.localtime(booking.created_at):%d/%m/%Y}</p>"
                f"<table><tr><th>Concepto</th><th class='n'>Importe</th></tr>{table}</table>"
                f"<p class='muted'>Imparte: {escape(booking.experience.provider.display_name)}. Fechas:</p><ul>{sessions}</ul>"
                f"<p class='muted'>Pago {escape(payment.external_id if payment else '-')} · Estado: {escape(STATUS_ES.get(booking.status, booking.status))}</p>")
        return "text/html; charset=utf-8", self._page("Comprobante de pago", body)

    def provider_statement(self, provider, month):
        from apps.payments.models import Transfer

        start = timezone.make_aware(timezone.datetime(month.year, month.month, 1))
        end = timezone.make_aware(timezone.datetime(month.year + (month.month == 12), month.month % 12 + 1, 1))
        transfers = (Transfer.objects.filter(provider=provider, release_at__gte=start, release_at__lt=end)
                     .exclude(status="canceled").select_related("booking__experience").order_by("release_at"))
        rows = "".join(
            f"<tr><td>{timezone.localtime(t.release_at):%d/%m}</td><td>{escape(t.booking.experience.title)} ({t.booking.code})</td>"
            f"<td class='n'>{_money(t.gross_cents)}</td><td class='n'>{_money(t.isr_withheld_cents + t.iva_withheld_cents)}</td>"
            f"<td class='n'>{_money(t.net_cents)}</td><td>{escape(STATUS_ES.get(t.status, t.status))}</td></tr>"
            for t in transfers
        )
        totals = transfers.aggregate(g=Sum("gross_cents"), i=Sum("isr_withheld_cents"), v=Sum("iva_withheld_cents"), n=Sum("net_cents"))
        tax = getattr(provider, "tax_profile", None)
        body = (f"<p class='muted'>{escape(provider.display_name)} · RFC {escape(tax.rfc if tax else 'pendiente')} · {month:%m/%Y}</p>"
                f"<table><tr><th>Fecha</th><th>Reserva</th><th class='n'>Precio</th><th class='n'>Retenciones</th>"
                f"<th class='n'>Depósito</th><th>Estado</th></tr>{rows}"
                f"<tr class='total'><td></td><td>Total</td><td class='n'>{_money(totals['g'] or 0)}</td>"
                f"<td class='n'>{_money((totals['i'] or 0) + (totals['v'] or 0))}</td><td class='n'>{_money(totals['n'] or 0)}</td><td></td></tr></table>"
                f"<p class='muted'>ISR retenido: {_money(totals['i'] or 0)} · IVA retenido: {_money(totals['v'] or 0)}. "
                f"La constancia de retenciones (CFDI) se emitirá cuando la facturación esté habilitada.</p>")
        return "text/html; charset=utf-8", self._page(f"Estado de cuenta {month:%m/%Y}", body)


def get_receipt_backend() -> ReceiptBackend:
    return import_string(settings.RECEIPT_BACKEND)()
