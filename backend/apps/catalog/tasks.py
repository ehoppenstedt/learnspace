from procrastinate.contrib.django import app


@app.task(queue="media", retry=2)
def process_media_task(asset_id: str):
    from apps.catalog import media

    media.process(asset_id)


@app.periodic(cron="15 3 * * *")
@app.task(queue="maintenance")
def expire_experiences_task(timestamp: int):
    from apps.catalog import services

    services.expire_experiences()
    services.refresh_all_denorm()
