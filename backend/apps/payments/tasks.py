from procrastinate.contrib.django import app


@app.task(queue="payments", retry=5)
def process_webhook_task(webhook_id: str):
    from apps.payments.services import process_webhook

    process_webhook(webhook_id)


@app.task(queue="payments", retry=5)
def execute_refund_task(refund_id: str):
    from apps.payments.services import execute_refund

    execute_refund(refund_id)


@app.task(queue="payments", retry=5)
def cancel_authorization_task(payment_id: str):
    from apps.payments.gateways import get_gateway
    from apps.payments.models import Payment

    payment = Payment.objects.get(pk=payment_id)
    get_gateway(payment.gateway).cancel_authorization(payment.external_id)


@app.task(queue="payments", retry=5)
def reverse_transfer_task(transfer_id: str, amount_cents: int):
    from apps.payments.gateways import get_gateway
    from apps.payments.models import Transfer

    transfer = Transfer.objects.get(pk=transfer_id)
    get_gateway().reverse_transfer(transfer_external_id=transfer.external_id, amount_cents=amount_cents,
                                   idempotency_key=f"reverse-{transfer.pk}-{transfer.reversed_cents}")


@app.periodic(cron="7 * * * *")
@app.task(queue="payments")
def release_transfers_task(timestamp: int):
    from apps.payments.services import release_due_transfers

    release_due_transfers()
