import os
import secrets
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or secrets.token_urlsafe(48)
DEBUG = os.environ.get("DJANGO_DEBUG") == "1"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "events",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
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
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_TZ = True

engine = os.environ.get("DATABASE_ENGINE", "sqlite")
if engine == "mysql":
    required = ("NAME", "USER", "PASSWORD", "HOST", "PORT")
    missing = [f"DATABASE_{field}" for field in required if not os.environ.get(f"DATABASE_{field}")]
    if missing:
        raise ImproperlyConfigured(f"Missing MySQL settings: {', '.join(missing)}")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            **{field: os.environ[f"DATABASE_{field}"] for field in required},
            "OPTIONS": {"charset": "utf8mb4", "isolation_level": "read committed"},
        },
    }
elif engine == "sqlite":
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"},
    }
else:
    raise ImproperlyConfigured("DATABASE_ENGINE must be 'mysql' or 'sqlite'.")
