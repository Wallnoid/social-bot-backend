"""
Local development settings.

These settings extend base.py for local development.
PostgreSQL is used via Docker for consistency with production.
"""

from .base import *  # noqa: F401, F403
from .base import env

# =============================================================================
# DEBUG
# =============================================================================

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

# =============================================================================
# DATABASE (PostgreSQL via Docker)
# =============================================================================

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://postgres:postgres@localhost:5432/social_bot",
    ),
}

# =============================================================================
# DEVELOPMENT EXTRAS
# =============================================================================

# Uncomment to add development-only apps:
# INSTALLED_APPS += [
#     "django_extensions",
# ]

# Add browsable API renderer in development
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
)

# =============================================================================
# CORS (Allow all in development)
# =============================================================================

CORS_ALLOW_ALL_ORIGINS = True

# =============================================================================
# EMAIL (Console backend for development)
# =============================================================================

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# =============================================================================
# CACHING (Local Memory)
# =============================================================================

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    }
}

# =============================================================================
# CELERY (Redis via Docker)
# =============================================================================

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")

# Execute tasks synchronously in development for easier debugging
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)
CELERY_TASK_EAGER_PROPAGATES = True

# =============================================================================
# THROTTLING (Relaxed for development)
# =============================================================================

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {  # noqa: F405
    "anon": "1000/hour",
    "user": "10000/hour",
}

# =============================================================================
# LOGGING (More verbose in development)
# =============================================================================

LOGGING["loggers"]["apps"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["django.db.backends"] = {  # noqa: F405
    "handlers": ["console"],
    "level": "WARNING",  # Set to DEBUG to see SQL queries
    "propagate": False,
}
