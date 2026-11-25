from django.conf import settings


def test_test_settings_are_loaded() -> None:
    assert settings.SETTINGS_MODULE == "config.settings.test"
    assert settings.LANGUAGE_CODE == "ru"
    assert settings.TIME_ZONE == "Europe/Moscow"
    assert settings.USE_TZ is True


def test_prod_static_storage_hashes_js_imports() -> None:
    from apps.core.storage import HashedStaticFilesStorage

    assert HashedStaticFilesStorage.support_js_module_import_aggregation is True


def test_hsts_flags_are_off_unless_configured() -> None:
    assert settings.SECURE_HSTS_INCLUDE_SUBDOMAINS is False
    assert settings.SECURE_HSTS_PRELOAD is False


def test_prod_hsts_flags_follow_the_environment() -> None:
    import os
    import subprocess
    import sys

    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
    env["DJANGO_HSTS_INCLUDE_SUBDOMAINS"] = "1"
    env["DJANGO_HSTS_PRELOAD"] = "0"
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import django; django.setup(); "
            "from django.conf import settings; "
            "print(int(settings.SECURE_HSTS_INCLUDE_SUBDOMAINS), "
            "int(settings.SECURE_HSTS_PRELOAD))",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.stdout.strip() == "1 0"


def test_prod_hosts_keep_the_internal_health_check() -> None:
    import os
    import subprocess
    import sys

    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
    env["DJANGO_ALLOWED_HOSTS"] = "203.0.113.10"
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import django; django.setup(); "
            "from django.conf import settings; "
            "print(','.join(settings.ALLOWED_HOSTS))",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.stdout.strip() == "203.0.113.10,127.0.0.1,localhost"


def test_whitenoise_follows_security_middleware() -> None:
    assert settings.MIDDLEWARE[0] == "django.middleware.security.SecurityMiddleware"
    assert settings.MIDDLEWARE[1] == "whitenoise.middleware.WhiteNoiseMiddleware"
