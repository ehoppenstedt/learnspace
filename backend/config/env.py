"""Tiny environment-variable helpers. Avoids a dependency for something this small."""

import os
from urllib.parse import parse_qs, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

_TRUE = {"1", "true", "yes", "on"}


def env_str(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise ImproperlyConfigured(f"Missing required environment variable {name}")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in _TRUE


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return default if value is None else int(value)


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def parse_database_url(url: str) -> dict:
    """postgis://user:pass@host:5432/name?sslmode=require -> Django DATABASES entry."""
    parsed = urlparse(url)
    if parsed.scheme not in {"postgis", "postgres", "postgresql"}:
        raise ImproperlyConfigured(f"Unsupported DATABASE_URL scheme {parsed.scheme!r}")
    options = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
    return {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
        "OPTIONS": options,
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
