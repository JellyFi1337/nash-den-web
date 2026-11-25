"""Общие настройки Django. Значения приходят из окружения."""

from pathlib import Path

import environ

# src/config/settings/base.py → каталог src
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()


def _csv(name: str) -> list[str]:
    """Значения через запятую. Пустая переменная даёт пустой список."""
    raw = env(name, default="")
    return [item.strip() for item in raw.split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
# Проверка здоровья контейнера и smoke ходят изнутри на 127.0.0.1:8000.
# Без этих имён сайт с одним IP или доменом в .env никогда не стал бы здоровым.
ALLOWED_HOSTS = list(dict.fromkeys([*_csv("DJANGO_ALLOWED_HOSTS"), "127.0.0.1", "localhost"]))
CSRF_TRUSTED_ORIGINS = _csv("DJANGO_CSRF_TRUSTED_ORIGINS")

_admin_path = env("DJANGO_ADMIN_PATH", default="dkr-admin/").strip("/")
ADMIN_PATH = f"{_admin_path}/"

LANGUAGE_CODE = "ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST"),
        "PORT": env("POSTGRES_PORT"),
        # Иначе остановленная база держит запрос дольше, чем страница ошибки.
        "OPTIONS": {"connect_timeout": 3},
    },
}

# Одна строка в stdout: время, уровень, имя. Тела запросов, cookies и секреты сюда не входят.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "line": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "formatter": "line",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "django.request": {
            "handlers": ["stdout"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["stdout"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["stdout"],
            "level": "INFO",
            # propagate оставлен: тесты и корневой журнал тоже видят запись, в stdout она одна.
            "propagate": True,
        },
    },
}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.team",
    "apps.access",
    "apps.journal",
    "apps.project",
    "apps.web",
    "apps.tgbot",
    "apps.sheet",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.access.middleware.PrivacyHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.access.csp.ContentSecurityPolicyMiddleware",
    "apps.access.middleware.DayCodeGateMiddleware",
]

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 2
SESSION_COOKIE_NAME = "nashden_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

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
                "apps.web.context.shell",
            ],
        },
    },
]

# Исходная статика — в репозитории. Сборка и загрузки — вне смонтированного src:
# media лежит на томе Docker.
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = Path("/app/staticfiles")
MEDIA_URL = "media/"
MEDIA_ROOT = Path("/app/media")

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_COOKIE_SECURE = env.bool("DJANGO_SECURE_COOKIES", default=False)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
CSRF_FAILURE_VIEW = "apps.web.views.csrf_failure"
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=0)
# Поддомены и preload — только для своего домена, после проверки. Чужой DNS их не включает.
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_HSTS_PRELOAD", default=False)
# HTTPS включает Caddy. Внутри сети контейнеров здоровье проверяется по HTTP.
SECURE_SSL_REDIRECT = False

TRUSTED_PROXY_COUNT = env.int("TRUSTED_PROXY_COUNT", default=0)
if TRUSTED_PROXY_COUNT > 0:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True

# Секреты и внешние адреса. Код читает их только отсюда, не из os.environ.
SITE_URL = env("SITE_URL", default="")
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_BOT_USERNAME = env("TELEGRAM_BOT_USERNAME", default="")
TELEGRAM_OWNER_ID = env("TELEGRAM_OWNER_ID", default="")
# Утренняя рассылка кода всем, кто нажал «Начать». По умолчанию выключена: код берут у бота сами.
CODE_BROADCAST = env.bool("CODE_BROADCAST", default=False)
CHATS_CONFIG = env("CHATS_CONFIG", default="/app/private/chats.toml")
SHEET_URL = env("SHEET_URL", default="")
SHEET_TTL = env.int("SHEET_TTL", default=900)
SHEET_TIMEOUT = env.int("SHEET_TIMEOUT", default=10)
