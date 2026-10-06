from procrastinate.contrib.django import app


@app.task(queue="notifications", retry=3)
def send_decision_email_task(experience_id: str, decision: str):
    from apps.moderation.notifications import send_decision_email

    send_decision_email(experience_id, decision)
