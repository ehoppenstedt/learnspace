from procrastinate.contrib.django import app


@app.periodic(cron="25 * * * *")
@app.task(queue="booking")
def reveal_reviews_task(timestamp: int):
    from apps.reviews.services import reveal_closed_windows

    reveal_closed_windows()
