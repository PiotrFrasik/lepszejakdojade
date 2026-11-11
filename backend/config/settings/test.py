"""Settings for the pytest suite."""

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = SECRET_KEY or "test-insecure-key"  # noqa: F405
ALLOWED_HOSTS = ["*"]

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
