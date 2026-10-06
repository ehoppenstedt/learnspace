from procrastinate.contrib.django import app


@app.task(queue="notifications", retry=3)
def send_notification_task(notification_id: str):
    from apps.notifications.services import send

    send(notification_id)
