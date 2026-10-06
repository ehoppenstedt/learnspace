"""Django settings. Every deploy-specific value comes from environment variables."""

from datetime import timedelta
from pathlib import Path

from config.env import env_bool, env_int, env_list, env_str, parse_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = env_str("SECRET_KEY", "dev-insecure-secret-key-change-me")
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,10.0.2.2")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
DEV_CORS_ORIGINS = env_list("DEV_CORS_ORIGINS")  # Expo web preview only; ignored unless DEBUG
PUBLIC_BASE_URL = env_str("PUBLIC_BASE_URL", "http://localhost:8000")

# --- Brand / legal (placeholders until the operating entity is final) ---------
BRAND_NAME = env_str("BRAND_NAME", "learnspace")
LEGAL_ENTITY_NAME = env_str("LEGAL_ENTITY_NAME", "RAZON SOCIAL PENDIENTE")
LEGAL_RFC = env_str("LEGAL_RFC", "RFC_PENDIENTE")
PRIVACY_NOTICE_VERSION = env_str("PRIVACY_NOTICE_VERSION", "2026-10-draft")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "django.contrib.postgres",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "procrastinate.contrib.django",
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.payments",
    "apps.booking",
    "apps.reviews",
    "apps.messaging",
    "apps.moderation",
]

MIDDLEWARE = [
    "apps.core.middleware.DevCorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.RequestLogMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": parse_database_url(
        env_str("DATABASE_URL", "postgis://learnspace:learnspace@localhost:5432/learnspace")
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# DB-backed cache: used by DRF throttling. Keeps Redis out of the stack.
CACHES = {
    "default": {
        "BACKEND": env_str("CACHE_BACKEND", "django.core.cache.backends.db.DatabaseCache"),
        "LOCATION": "cache_table",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# --- i18n ---------------------------------------------------------------------
LANGUAGE_CODE = "es"
LANGUAGES = [("es", "Español"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- API ------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "otp_request_ip": env_str("THROTTLE_OTP_REQUEST_IP", "10/hour"),
        "auth_ip": env_str("THROTTLE_AUTH_IP", "20/hour"),
        "otp_verify_ip": env_str("THROTTLE_OTP_VERIFY_IP", "30/hour"),
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_MINUTES", 15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_DAYS", 30)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "SIGNING_KEY": env_str("JWT_SIGNING_KEY", SECRET_KEY),
}

# --- Auth: OTP + social ---------------------------------------------------------
OTP_TTL_SECONDS = env_int("OTP_TTL_SECONDS", 600)
OTP_MAX_ATTEMPTS = env_int("OTP_MAX_ATTEMPTS", 5)
OTP_MAX_PER_DESTINATION = env_int("OTP_MAX_PER_DESTINATION", 3)
OTP_DESTINATION_WINDOW_SECONDS = env_int("OTP_DESTINATION_WINDOW_SECONDS", 600)
SMS_BACKEND = env_str("SMS_BACKEND", "apps.accounts.sms.ConsoleSMSBackend")
APPLE_CLIENT_IDS = env_list("APPLE_CLIENT_IDS", "com.learnspace.app")
GOOGLE_CLIENT_IDS = env_list("GOOGLE_CLIENT_IDS")
MIN_AGE_YEARS = 18

# --- Email ----------------------------------------------------------------------
EMAIL_BACKEND = env_str("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env_str("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env_str("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env_str("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env_str("DEFAULT_FROM_EMAIL", "learnspace <no-reply@learnspace.local>")

# --- Field encryption (AES-256-GCM). Format: "kid:base64key,kid2:base64key2". ----
# The first key encrypts; all keys decrypt (rotation).
FIELD_ENCRYPTION_KEYS = env_str(
    "FIELD_ENCRYPTION_KEYS", "dev:ZGV2LW9ubHkta2V5LWRvLW5vdC11c2UtaW4tcHJvZCE="
)

# --- Media ----------------------------------------------------------------------
MEDIA_STORAGE = env_str("MEDIA_STORAGE", "local")  # "local" | "s3"
MEDIA_ROOT = Path(env_str("MEDIA_ROOT", str(BASE_DIR / "var" / "media")))
S3_BUCKET = env_str("S3_BUCKET", "")
S3_ENDPOINT_URL = env_str("S3_ENDPOINT_URL", "") or None
S3_REGION = env_str("S3_REGION", "auto")
S3_ACCESS_KEY_ID = env_str("S3_ACCESS_KEY_ID", "")
S3_SECRET_ACCESS_KEY = env_str("S3_SECRET_ACCESS_KEY", "")
MEDIA_UPLOAD_URL_TTL = env_int("MEDIA_UPLOAD_URL_TTL", 300)
MEDIA_READ_URL_TTL = env_int("MEDIA_READ_URL_TTL", 3600)
MEDIA_MAX_IMAGE_BYTES = env_int("MEDIA_MAX_IMAGE_BYTES", 15 * 1024 * 1024)
MEDIA_MAX_VIDEO_BYTES = env_int("MEDIA_MAX_VIDEO_BYTES", 100 * 1024 * 1024)
MEDIA_MAX_VIDEO_SECONDS = env_int("MEDIA_MAX_VIDEO_SECONDS", 60)
MEDIA_MAX_IMAGES_PER_EXPERIENCE = 10
MEDIA_MAX_VIDEOS_PER_EXPERIENCE = 3
FFMPEG_BINARY = env_str("FFMPEG_BINARY", "ffmpeg")
FFPROBE_BINARY = env_str("FFPROBE_BINARY", "ffprobe")

# --- Marketplace --------------------------------------------------------------------
DEFAULT_FEE_BPS = env_int("DEFAULT_FEE_BPS", 500)  # used only if no FeeConfig row exists
FEATURE_ONLINE_EXPERIENCES = env_bool("FEATURE_ONLINE_EXPERIENCES", False)
FEED_DEFAULT_RADIUS_KM = 10
FEED_MAX_RADIUS_KM = 50
FEED_PAGE_SIZE = 20
FEED_MAX_OFFSET = 1000
MAP_MAX_PINS = 300

# --- Jobs ---------------------------------------------------------------------------
PROCRASTINATE_ON_APP_READY = "apps.core.jobs.on_app_ready"

# --- Security -----------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# --- Observability --------------------------------------------------------------------
LOG_LEVEL = env_str("LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "apps.core.logging.JSONFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {"django.db.backends": {"level": "WARNING"}, "procrastinate": {"level": "WARNING"}},
}

SENTRY_DSN = env_str("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env_str("SENTRY_ENVIRONMENT", "development"),
        traces_sample_rate=float(env_str("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
        send_default_pii=False,
    )
