"""
Base settings for the Django project.

These settings are shared across all environments (local, production, etc.).
Environment-specific settings should override values in their respective files.
"""

import os
from datetime import timedelta
from pathlib import Path

import environ
from corsheaders.defaults import default_headers
from django.core.exceptions import ImproperlyConfigured

# =============================================================================
# PATH CONFIGURATION
# =============================================================================

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Ensure logs directory exists
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# =============================================================================
# ENVIRONMENT VARIABLES
# =============================================================================

env = environ.Env(
    # Set casting and default values
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
)

# Read .env file if it exists
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

# =============================================================================
# CORE SETTINGS
# =============================================================================

SECRET_KEY = env("DJANGO_SECRET_KEY", default="change-me-in-production")

DEBUG = env("DEBUG")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# =============================================================================
# APPLICATION DEFINITION
# =============================================================================

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "health_check",
    "django_celery_beat",
    "wanps.messaging",
    "wanps.whatsapp",
    "wanps.messenger",
    "wanps.instagram",
    "wanps.inbox",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.tenants",
    "apps.channels",
    "apps.conversations",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# =============================================================================
# MIDDLEWARE
# =============================================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves the static files (the styles of the admin) from the app itself
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.RequestLoggingMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# =============================================================================
# DATABASE
# =============================================================================

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://postgres:postgres@localhost:5432/social_bot",
    ),
}

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =============================================================================
# AUTHENTICATION
# =============================================================================

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# =============================================================================
# INTERNATIONALIZATION
# =============================================================================

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

# =============================================================================
# STATIC & MEDIA FILES
# =============================================================================

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
# Where the saved files go. Empty means `media/` in the project; set it to put them on another disk
MEDIA_ROOT = Path(env("MEDIA_ROOT", default="") or BASE_DIR / "media")

# The files that clients send are saved the first time someone opens them (see apps/conversations/files.py)
MESSAGE_FILE_MAX_BYTES = env.int("MESSAGE_FILE_MAX_BYTES", default=16 * 1024 * 1024)
MESSAGE_FILE_RETENTION_DAYS = env.int("MESSAGE_FILE_RETENTION_DAYS", default=30)

# =============================================================================
# DJANGO REST FRAMEWORK
# =============================================================================

REST_FRAMEWORK = {
    # Authentication
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    # Permissions
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    # Pagination
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    # Filtering
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    # Throttling
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
    # How many reverse proxies sit in front of the API. With 0 the limits identify a client by
    # its socket address. Never leave it unset: DRF would then trust the whole X-Forwarded-For
    # header, which the client controls, and could be dodged by changing it. Behind a proxy set
    # it to their number, or every user shares the proxy's address and one limit.
    "NUM_PROXIES": env.int("NUM_PROXIES", default=0),
    # Schema
    "DEFAULT_SCHEMA_CLASS": "apps.tenants.schema.TenantAutoSchema",
    # Renderers
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
    # Exception handling
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    # Versioning
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
    # Date/Time formats
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%S%z",
    "DATE_FORMAT": "%Y-%m-%d",
}

# =============================================================================
# SIMPLE JWT
# =============================================================================

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_OBTAIN_SERIALIZER": "rest_framework_simplejwt.serializers.TokenObtainPairSerializer",
    # Tokens carry a claim derived from the password hash: changing the password cuts every
    # session at once. Our refresh serializer checks the claim too (SimpleJWT only checks access).
    "CHECK_REVOKE_TOKEN": True,
    "TOKEN_REFRESH_SERIALIZER": "apps.accounts.serializers.TokenRefreshSerializer",
}

# The refresh token travels in an httpOnly cookie, never in a response body. The cookie only
# goes to the authentication routes and to the API host (no Domain), so the frontend and the
# API must share a base domain (app.example.com / api.example.com).
AUTH_REFRESH_COOKIE_NAME = "refresh_token"
AUTH_REFRESH_COOKIE_PATH = "/api/v1/accounts/"
AUTH_REFRESH_COOKIE_SECURE = env.bool("AUTH_REFRESH_COOKIE_SECURE", default=False)

# =============================================================================
# DRF SPECTACULAR (API DOCUMENTATION)
# =============================================================================

SPECTACULAR_SETTINGS = {
    "TITLE": "Social Bot API",
    "DESCRIPTION": "Backend API for the Social Bot suite: WhatsApp, Messenger and Instagram "
    "conversations, calendar, CRM and notifications.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/",
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": True,
    },
}

# =============================================================================
# CORS
# =============================================================================

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True
# A browser on another origin may send, besides the usual ones, the header that names the
# active business: without it the browser rejects every request of a business.
CORS_ALLOW_HEADERS = (*default_headers, "x-tenant-id")

# Base URL of the frontend, used in links sent by email
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:3000")

# Seconds a password link (e.g. the one emailed to a new admin) stays valid
PASSWORD_RESET_TIMEOUT = env.int("PASSWORD_RESET_TIMEOUT", default=60 * 60 * 24 * 7)

# Channels (wanps-core): many accounts stored in the database, secrets encrypted with this key
WANPS_MULTITENANT = True
WANPS_ENCRYPTION_KEY = env("WANPS_ENCRYPTION_KEY", default="")
if not WANPS_ENCRYPTION_KEY:
    # Fail at startup, not on the first save of a token or Meta App secret
    raise ImproperlyConfigured("Set WANPS_ENCRYPTION_KEY in .env (see .env.example).")

# The AI that answers for every account that has none of its own (Social Bot pays for it). Empty
# values are left out, so a missing provider or key fails with a clear error when the bot is used.
WANPS_AI = {
    key: value
    for key, value in {
        "PROVIDER": env("WANPS_AI_PROVIDER", default=""),
        "API_KEY": env("WANPS_AI_API_KEY", default=""),
        "MODEL": env("WANPS_AI_MODEL", default=""),
        "EFFORT": env("WANPS_AI_EFFORT", default="low"),
        # Seconds to wait for the AI: a slow provider must not hold the worker for long
        "TIMEOUT": env.float("WANPS_AI_TIMEOUT", default=30),
    }.items()
    if value
}

# The bot of every account. Fixed here, not read from `.env`: it is code of this project.
WANPS_HANDLER = "apps.channels.handler.ChannelAIHandler"

# The calls the bot makes to the endpoints of its tools: seconds in total for each one, bytes of
# answer it reads at most (the answer travels to the AI), and days its record is kept.
TOOL_CALL_TIMEOUT = env.float("TOOL_CALL_TIMEOUT", default=5)
TOOL_CALL_MAX_BYTES = env.int("TOOL_CALL_MAX_BYTES", default=64 * 1024)
TOOL_CALL_RETENTION_DAYS = env.int("TOOL_CALL_RETENTION_DAYS", default=30)

# Minutes the bot stays silent in a chat after a person replies from the inbox; once they pass
# without another reply of a person, the bot answers the client again
BOT_RESUME_AFTER_MINUTES = env.int("BOT_RESUME_AFTER_MINUTES", default=60)

# The time zone the bot tells the date and the time in (the businesses are in Ecuador for now)
BUSINESS_TIME_ZONE = env("BUSINESS_TIME_ZONE", default="America/Guayaquil")

# A client who insists on messages unrelated to the business: faults before the block, the fault
# from which the bot warns, hours without a new fault after which they expire, and the minutes of
# the block (longer when the same client is blocked again within those hours)
# Messages a client may send in an hour before the bot stops answering them (no AI is called)
BOT_MAX_MESSAGES_PER_HOUR = env.int("BOT_MAX_MESSAGES_PER_HOUR", default=20)
# Replies the bots of a business may send in a day (a business can have its own number): the last
# defence of the AI spending. Then the bots stay silent until the next day and no AI is called
BOT_MAX_REPLIES_PER_DAY = env.int("BOT_MAX_REPLIES_PER_DAY", default=500)
BOT_MAX_STRIKES = env.int("BOT_MAX_STRIKES", default=5)
BOT_WARN_FROM_STRIKE = env.int("BOT_WARN_FROM_STRIKE", default=2)
BOT_STRIKES_EXPIRE_HOURS = env.int("BOT_STRIKES_EXPIRE_HOURS", default=24)
BOT_BLOCK_MINUTES = env.int("BOT_BLOCK_MINUTES", default=60)
BOT_REPEAT_BLOCK_MINUTES = env.int("BOT_REPEAT_BLOCK_MINUTES", default=24 * 60)

# Process the messages of the clients (bot replies included) in a Celery worker instead of inside the
# webhook request, so Meta gets its answer at once. An account can override it in the admin.
WANPS_ASYNC = env.bool("WANPS_ASYNC", default=False)

# Seconds an invitation to join a business stays valid
INVITATION_TIMEOUT = env.int("INVITATION_TIMEOUT", default=60 * 60 * 24 * 7)

# =============================================================================
# EMAIL (SMTP; the backend itself is chosen in local.py / production.py)
# =============================================================================

EMAIL_HOST = env("EMAIL_HOST", default="smtp.hostinger.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=465)
# STARTTLS (usually port 587) and SSL (usually port 465) are mutually exclusive
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=True)
# Seconds to wait for the mail server; without it a stalled server blocks the request
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Social Bot <contact@wanps.tech>")

# =============================================================================
# CELERY
# =============================================================================

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BEAT_SCHEDULE = {
    "delete-expired-message-files": {
        "task": "apps.conversations.tasks.delete_expired_message_files",
        "schedule": 24 * 60 * 60,  # every day
    },
    "flush-expired-tokens": {
        "task": "apps.accounts.tasks.flush_expired_tokens",
        "schedule": 24 * 60 * 60,  # every day
    },
    "delete-old-tool-calls": {
        "task": "apps.channels.tasks.delete_old_tool_calls",
        "schedule": 24 * 60 * 60,  # every day
    },
}

# =============================================================================
# CACHING
# =============================================================================

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/1"),
        "OPTIONS": {
            "db": "1",
        },
    },
    # Connection permits of the inbox in real time. Always in Redis, because the permit is asked
    # of one process and used on another, which a per-process cache cannot do
    "ws_tickets": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/1"),
        "OPTIONS": {"db": "2"},
    },
}

# Delivers the events of the inbox between processes (the webhook runs in web, the bot in the worker)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                {
                    "address": env("REDIS_URL", default="redis://localhost:6379/1"),
                    # An idle connection waits 5 seconds at a time for a message. redis-py 8 cuts
                    # every read after 5 seconds by default, which closed each socket that long
                    "socket_timeout": 10,
                }
            ]
        },
    },
}

# Seconds a connection permit can be used after it is asked for
WS_TICKET_TIMEOUT = env.int("WS_TICKET_TIMEOUT", default=30)

# =============================================================================
# LOGGING
# =============================================================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {asctime} {message}",
            "style": "{",
        },
    },
    "filters": {
        "require_debug_true": {
            "()": "django.utils.log.RequireDebugTrue",
        },
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "file": {
            "level": "WARNING",
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs" / "django.log",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "file"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
