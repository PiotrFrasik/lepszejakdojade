"""Local development settings."""

from .base import *  # noqa: F403
from .base import env_bool, env_list

DEBUG = env_bool("DJANGO_DEBUG", default=True)
SECRET_KEY = SECRET_KEY or "dev-insecure-change-me"  # noqa: F405
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,backend")

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]
