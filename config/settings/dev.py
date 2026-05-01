from .base import *  # noqa

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# Console emails in dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Permissive CORS in dev
CORS_ALLOW_ALL_ORIGINS = True
