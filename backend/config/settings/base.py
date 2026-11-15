"""Settings shared by every environment. Values come from environment variables."""

import math
import os
from pathlib import Path

from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def env_float(name: str, default: float, min_value: float | None = None) -> float:
    """A finite number from the environment; unset or blank means ``default``."""
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        number = float(value)
    except ValueError:
        raise ImproperlyConfigured(f"{name} must be a number, got {value!r}") from None
    if not math.isfinite(number):
        raise ImproperlyConfigured(f"{name} must be a finite number, got {value!r}")
    if min_value is not None and number < min_value:
        raise ImproperlyConfigured(f"{name} must be at least {min_value}, got {value!r}")
    return number


# Core
SECRET_KEY = env_str("DJANGO_SECRET_KEY")
DEBUG = env_bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")

APP_VERSION = env_str("APP_VERSION", "dev")

INSTALLED_APPS = [
    # Must come before django.contrib.admin (translated fields in admin forms).
    "modeltranslation",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    # Third party
    "rest_framework",
    "drf_spectacular",
    # Local
    "core",
    "cities",
    "transit_data",
    "timetable",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Language from Accept-Language only (replaces django.middleware.locale.LocaleMiddleware).
    "core.middleware.AcceptLanguageMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database (PostgreSQL + PostGIS)
DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": env_str("POSTGRES_DB", "lepszejakdojade"),
        "USER": env_str("POSTGRES_USER", "lepszejakdojade"),
        "PASSWORD": env_str("POSTGRES_PASSWORD"),
        "HOST": env_str("POSTGRES_HOST", "localhost"),
        "PORT": env_str("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {"connect_timeout": 5},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalisation. The request language comes only from Accept-Language
# (core.middleware.AcceptLanguageMiddleware); LANGUAGE_CODE is the fallback.
LANGUAGE_CODE = "pl"
LANGUAGES = [
    ("pl", _("Polish")),
    ("en", _("English")),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True

# Translated model fields (django-modeltranslation): one column per language,
# e.g. name_pl / name_en. Reading `name` returns the active language and falls
# back to Polish when the translation is empty. See core.serializers.TranslatedModelSerializer.
MODELTRANSLATION_DEFAULT_LANGUAGE = "pl"
MODELTRANSLATION_LANGUAGES = ("pl", "en")
MODELTRANSLATION_FALLBACK_LANGUAGES = ("pl",)
TIME_ZONE = "Europe/Warsaw"
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Redis / Celery
REDIS_URL = env_str("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# City configuration: one YAML file per city (see cities/registry.py)
CITY_CONFIG_DIR = Path(env_str("CITY_CONFIG_DIR") or BASE_DIR / "cities" / "config")

# External services
# DEPRECATED: one OpenTripPlanner instance per city. Use cities.registry.get_otp_url(city_id),
# which reads OTP_URL_<CITY_ID> (e.g. OTP_URL_KRAKOW). Removed once compose drops it (#47).
OTP_URL = env_str("OTP_URL", "http://localhost:8080")

# OpenTripPlanner graph build. In containers ./otp is mounted at /otp.
# Config directory (build-config.json, router-config.json, ...).
OTP_CONFIG_DIR = Path(env_str("OTP_CONFIG_DIR") or BASE_DIR.parent / "otp")
# Working directory: per-city OSM extracts, GTFS copies and built graphs.
OTP_DATA_DIR = Path(env_str("OTP_DATA_DIR") or BASE_DIR.parent / "otp" / "data")
# osmium-tool executable used to clip the OSM extract.
OTP_OSMIUM_BIN = env_str("OTP_OSMIUM_BIN").strip() or "osmium"
# Buffer (km) added around the GTFS stops' bounding box when clipping the OSM extract.
OTP_BBOX_BUFFER_KM = env_float("OTP_BBOX_BUFFER_KM", 3.0, min_value=0)

# Timeout (seconds) for dependency checks in the health endpoint
HEALTH_CHECK_TIMEOUT = 2

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "lepszejakdojade API",
    "DESCRIPTION": "Public transport API for Krakow and Warsaw.",
    "VERSION": APP_VERSION,
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]+",
    "ENUM_NAME_OVERRIDES": {
        "HealthStatusEnum": "core.serializers.HEALTH_STATUS_CHOICES",
        "VehicleTypeEnum": "cities.registry.VEHICLE_TYPES",
        "VariantKindEnum": "timetable.serializers.VARIANT_KINDS",
        "LineNoticeKindEnum": "timetable.serializers.LINE_NOTICE_KINDS",
    },
}

# Logging: everything to stdout, collected by docker
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "default"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# Realtime collector (transit_data)
REALTIME_POLL_INTERVAL_SECONDS = float(env_str("REALTIME_POLL_INTERVAL_SECONDS", "30"))
# Static GTFS import time, local to CELERY_TIMEZONE (Europe/Warsaw).
GTFS_IMPORT_HOUR = int(env_str("GTFS_IMPORT_HOUR", "3"))
GTFS_IMPORT_MINUTE = int(env_str("GTFS_IMPORT_MINUTE", "30"))
CELERY_BEAT_SCHEDULE = {
    "collect-trip-updates": {
        "task": "transit_data.collect_trip_updates",
        "schedule": REALTIME_POLL_INTERVAL_SECONDS,
        # Drop runs that waited longer than one interval instead of piling them up.
        "options": {"expires": REALTIME_POLL_INTERVAL_SECONDS},
    },
    # Nightly static GTFS import; Warsaw feed is a rolling 30-day window, so it must run daily.
    "import-gtfs-nightly": {
        "task": "transit_data.import_all_gtfs",
        "schedule": crontab(hour=GTFS_IMPORT_HOUR, minute=GTFS_IMPORT_MINUTE),
    },
}
