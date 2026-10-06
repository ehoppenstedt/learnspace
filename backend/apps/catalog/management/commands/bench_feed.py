"""Measures feed latency through the full Django stack (no network). Reports p50/p95/max.

    python manage.py bench_feed --requests 300
"""

import random
import statistics
import time

from django.core.management.base import BaseCommand
from django.test import Client
from django.test.utils import override_settings

from apps.catalog.models import Area


class Command(BaseCommand):
    help = "Benchmark /api/v1/experiences with randomized CDMX locations and filters."

    def add_arguments(self, parser):
        parser.add_argument("--requests", type=int, default=300)

    @override_settings(ALLOWED_HOSTS=["*"])
    def handle(self, *args, **opts):
        rng = random.Random(7)
        areas = list(Area.objects.all())
        client = Client()
        timings = []
        for i in range(opts["requests"]):
            area = rng.choice(areas)
            params = {"lat": area.centroid.y + rng.uniform(-0.01, 0.01), "lng": area.centroid.x + rng.uniform(-0.01, 0.01),
                      "radius_km": rng.choice([3, 5, 10, 20])}
            if i % 3 == 0:
                params["category"] = rng.choice(["art", "music", "cooking", "dance,sports"])
            if i % 4 == 0:
                params.update({"dow": "2,4", "time_from": "18:00", "time_to": "22:00"})
            if i % 5 == 0:
                params["price_max"] = 60000
            start = time.perf_counter()
            res = client.get("/api/v1/experiences", params)
            timings.append((time.perf_counter() - start) * 1000)
            assert res.status_code == 200, res.content
        timings.sort()
        p95 = timings[int(len(timings) * 0.95) - 1]
        self.stdout.write(
            f"n={len(timings)} p50={statistics.median(timings):.1f}ms p95={p95:.1f}ms max={timings[-1]:.1f}ms"
        )
