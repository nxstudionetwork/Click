"""
Click platform settings.

One settings module, configured entirely through environment variables
(12-factor). Production refuses to start without a real secret key and
explicit allowed hosts.
"""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path
import os
import sys

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader for local development. Real env vars always win."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
TESTING = env_bool("CLICK_TESTING", False) or "pytest" in sys.modules

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG or TESTING:
        SECRET_KEY = "insecure-dev-only-key-never-use-in-production-0000"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    # Click domains
    "apps.core",
    "apps.users",
    "apps.customers",
    "apps.stores",
    "apps.catalog",
    "apps.carts",
    "apps.orders",
    "apps.payments",
    "apps.wishlists",
    "apps.notifications",
    "apps.rewards",
    "apps.support",
    "apps.ai",
    "apps.wallet",
    "apps.bookings",
    "apps.identity",
    "apps.activity",
    "apps.partners",
    "apps.buzz",
    "apps.rides",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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

# PostgreSQL is the primary database. Connections are pooled per-process.
DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        default="postgres://click:click@localhost:5432/click",
        conn_max_age=60,
        conn_health_checks=True,
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "users.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
if TESTING:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# User uploads (profile photos). Local disk in development; object storage in production.
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# --- API ---------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["apps.core.api.renderers.CamelCaseJSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["apps.core.api.parsers.CamelCaseJSONParser"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.api.pagination.DefaultPagination",
    "EXCEPTION_HANDLER": "apps.core.api.exceptions.click_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.environ.get("THROTTLE_ANON", "120/min"),
        "user": os.environ.get("THROTTLE_USER", "600/min"),
        "auth": os.environ.get("THROTTLE_AUTH", "10/min"),  # login / register (credential guessing)
        "auth_session": os.environ.get("THROTTLE_AUTH_SESSION", "120/min"),  # refresh / logout run on every page load
        "partner_onboarding": os.environ.get("THROTTLE_PARTNER_ONBOARDING", "60/min"),
        "order_placement": os.environ.get("THROTTLE_ORDERS", "20/min"),
        "ai": os.environ.get("THROTTLE_AI", "20/min"),
        "quote": os.environ.get("THROTTLE_QUOTE", "60/min"),  # ride fare quotes
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}
if TESTING:
    REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("JWT_ACCESS_MINUTES", "10"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.environ.get("JWT_REFRESH_DAYS", "14"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "SIGNING_KEY": os.environ.get("JWT_SIGNING_KEY", SECRET_KEY),
    "USER_ID_FIELD": "id",
}

# Refresh tokens live only in an httpOnly cookie scoped to the auth endpoints;
# access tokens are short-lived and kept in memory by the frontend.
AUTH_REFRESH_COOKIE = {
    "name": "click_refresh",
    "path": "/api/v1/auth/",
    "secure": not DEBUG,
    "samesite": os.environ.get("AUTH_COOKIE_SAMESITE", "Lax"),
    "domain": os.environ.get("AUTH_COOKIE_DOMAIN") or None,
}

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173" if DEBUG else "")
CORS_ALLOW_CREDENTIALS = True
from corsheaders.defaults import default_headers  # noqa: E402

CORS_ALLOW_HEADERS = (*default_headers, "x-click-client", "idempotency-key")
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# --- Security hardening (production) ---------------------------------
if not DEBUG and not TESTING:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# --- Click business configuration ------------------------------------
CLICK_DEV_PORT = os.environ.get("CLICK_DEV_PORT", "4000")
# DEVELOPMENT-ONLY one-click login as the seeded test customer. Hard-wired off unless DEBUG is on,
# so it cannot be enabled in production even if the env var is set.
CLICK_DEV_LOGIN_ENABLED = DEBUG and env_bool("CLICK_DEV_LOGIN", True)
CLICK_DEV_TEST_CUSTOMER_EMAIL = "test.customer@click.local"

# --- Customer identity ------------------------------------------------
# Phone sign-in is verified by a pluggable identity provider; Click then issues its own session.
# To change provider later: add a verifier in apps/identity and point this mapping at it.
CLICK_IDENTITY_PROVIDERS = {
    "firebase": "apps.identity.firebase.FirebaseIdTokenVerifier",
}
# Firebase project whose ID tokens are accepted (public identifier, not a secret). No service-account key is needed:
# tokens are verified against Google's public certificates.
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "clickstartup26")
# Local Firebase Auth Emulator (e.g. "127.0.0.1:9099"). Honoured ONLY when DEBUG is on.
FIREBASE_AUTH_EMULATOR_HOST = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "") if DEBUG else ""
# Legacy email/password endpoints: development/test accounts only. Customers sign in with phone OTP.
CLICK_PASSWORD_AUTH_ENABLED = env_bool("CLICK_PASSWORD_AUTH", DEBUG or TESTING)
CLICK_DEFAULT_CURRENCY = os.environ.get("CLICK_DEFAULT_CURRENCY", "INR")
CLICK_TAX_RATE = Decimal(os.environ.get("CLICK_TAX_RATE", "0.05"))
# GST on platform convenience fees (bookings).
CLICK_SERVICE_FEE_TAX_RATE = Decimal(os.environ.get("CLICK_SERVICE_FEE_TAX_RATE", "0.18"))
CLICK_REWARD_POINTS_PER_100 = int(os.environ.get("CLICK_REWARD_POINTS_PER_100", "10"))
CLICK_REWARD_EXPIRY_DAYS = int(os.environ.get("CLICK_REWARD_EXPIRY_DAYS", "365"))
# Dotted path to an apps.ai.providers.AIProvider implementation. Default: Buddy basic mode
# (built-in, answers only from real Click data). Set to empty to disable AI.
CLICK_AI_PROVIDER = os.environ.get("CLICK_AI_PROVIDER", "apps.ai.buddy.ClickBasicBuddy")
# Speech-to-text for Buddy GO / voice search (dotted path to an apps.ai.speech.SpeechProvider). Empty = voice off.
CLICK_SPEECH_PROVIDER = os.environ.get("CLICK_SPEECH_PROVIDER", "")
# Image recognition for camera search. Empty = off (QR scanning still works on-device in the app).
CLICK_VISION_PROVIDER = os.environ.get("CLICK_VISION_PROVIDER", "")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
    "loggers": {"click.audit": {"handlers": ["console"], "level": "INFO", "propagate": False}},
}
