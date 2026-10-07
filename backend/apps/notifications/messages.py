"""Notification copy (es default, en). Kept in code so it is versioned and testable."""

MESSAGES = {
    "booking_confirmed": {
        "es": ("Reserva confirmada", "«{title}» · {when}. Ya puedes ver la dirección exacta en tu reserva {code}."),
        "en": ("Booking confirmed", "“{title}” · {when}. The exact address is now in your booking {code}."),
    },
    "booking_new_for_provider": {
        "es": ("Nueva reserva", "{learner} reservó {seats} lugar(es) en «{title}» · {when}."),
        "en": ("New booking", "{learner} booked {seats} spot(s) for “{title}” · {when}."),
    },
    "approval_requested": {
        "es": ("Reserva por aprobar", "{learner} quiere unirse a «{title}» · {when}. Tienes hasta {deadline} para responder."),
        "en": ("Booking to approve", "{learner} wants to join “{title}” · {when}. Please respond by {deadline}."),
    },
    "approval_pending_learner": {
        "es": ("Solicitud enviada", "Quien imparte «{title}» debe aprobar tu reserva. Solo cobraremos si la aprueba."),
        "en": ("Request sent", "The teacher of “{title}” needs to approve your booking. You're only charged if approved."),
    },
    "approval_declined": {
        "es": ("Reserva no aprobada", "Tu solicitud para «{title}» no fue aprobada. No se te cobró nada."),
        "en": ("Booking not approved", "Your request for “{title}” wasn't approved. You were not charged."),
    },
    "booking_cancelled_learner": {
        "es": ("Reserva cancelada", "Cancelaste «{title}». Reembolso: {refund}. Puede tardar de 5 a 10 días en tu estado de cuenta."),
        "en": ("Booking cancelled", "You cancelled “{title}”. Refund: {refund}. It can take 5-10 days to appear on your statement."),
    },
    "booking_cancelled_for_provider": {
        "es": ("Reserva cancelada", "{learner} canceló su lugar en «{title}» · {when}."),
        "en": ("Booking cancelled", "{learner} cancelled their spot in “{title}” · {when}."),
    },
    "session_cancelled_by_provider": {
        "es": ("Clase cancelada", "Quien imparte canceló «{title}» · {when}. Te reembolsamos {refund} completo."),
        "en": ("Class cancelled", "The teacher cancelled “{title}” · {when}. We refunded {refund} in full."),
    },
    "sold_out_refund": {
        "es": ("Lugar no disponible", "Se agotaron los lugares de «{title}» mientras pagabas. Te reembolsamos {refund} completo."),
        "en": ("Spot no longer available", "“{title}” sold out while you were paying. We refunded {refund} in full."),
    },
    "payment_failed": {
        "es": ("Pago no completado", "No pudimos cobrar tu reserva de «{title}». Intenta con otro método de pago."),
        "en": ("Payment not completed", "We couldn't charge your booking for “{title}”. Try another payment method."),
    },
    "reminder_24h": {
        "es": ("Mañana: {title}", "Tu clase es {when}. Dirección: {address}."),
        "en": ("Tomorrow: {title}", "Your class is {when}. Address: {address}."),
    },
    "reminder_2h": {
        "es": ("En 2 horas: {title}", "Empieza a las {time}. Dirección: {address}."),
        "en": ("In 2 hours: {title}", "Starts at {time}. Address: {address}."),
    },
    "experience_decision": {
        "es": ("Revisión de «{title}»", "{decision_text}"),
        "en": ("Review of “{title}”", "{decision_text}"),
    },
    "transfer_sent": {
        "es": ("Pago enviado", "Enviamos {net} por «{title}» ({code}). Llega en tu próximo depósito semanal."),
        "en": ("Payment sent", "We sent {net} for “{title}” ({code}). It arrives with your next weekly payout."),
    },
    "data_export_ready": {
        "es": ("Tus datos están listos", "Descarga tu archivo (válido 24 horas): {url}"),
        "en": ("Your data is ready", "Download your file (valid for 24 hours): {url}"),
    },
}

# Reminders can be turned off; transactional messages (money, confirmations) cannot.
OPTIONAL_KINDS = {"reminder_24h", "reminder_2h"}
