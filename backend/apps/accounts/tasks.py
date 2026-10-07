from procrastinate.contrib.django import app


@app.task(queue="maintenance", retry=2)
def data_export_task(user_id: str):
    from apps.accounts.privacy import run_export

    run_export(user_id)
