# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# GDAL/GEOS/PROJ for GeoDjango, ffmpeg for video processing.
RUN apt-get update \
 && apt-get install -y --no-install-recommends gdal-bin libgdal-dev libgeos-dev libproj-dev ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN SECRET_KEY=build DATABASE_URL=postgis://x:x@localhost/x python manage.py collectstatic --noinput

RUN useradd --create-home app && mkdir -p /app/var && chown -R app /app/var
USER app

EXPOSE 8000
# Override CMD for the worker: python manage.py procrastinate worker
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "30", "--access-logfile", "-"]
