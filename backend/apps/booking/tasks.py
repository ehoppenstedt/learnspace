from procrastinate.contrib.django import app


@app.periodic(cron="* * * * *")
@app.task(queue="booking")
def expire_holds_task(timestamp: int):
    from apps.booking.services import expire_holds

    expire_holds()


@app.periodic(cron="*/5 * * * *")
@app.task(queue="booking")
def expire_approvals_task(timestamp: int):
    from apps.booking.services import expire_approvals

    expire_approvals()


@app.periodic(cron="*/10 * * * *")
@app.task(queue="booking")
def expire_unpaid_task(timestamp: int):
    from apps.booking.services import expire_unpaid

    expire_unpaid()


@app.periodic(cron="*/5 * * * *")
@app.task(queue="notifications")
def reminders_task(timestamp: int):
    from apps.booking.services import send_reminders

    send_reminders()


@app.periodic(cron="20 * * * *")
@app.task(queue="booking")
def complete_bookings_task(timestamp: int):
    from apps.booking.services import complete_finished

    complete_finished()
