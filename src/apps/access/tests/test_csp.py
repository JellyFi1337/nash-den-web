from apps.access.csp import content_security_policy


def test_telegram_script_is_only_on_the_enter_page() -> None:
    home = content_security_policy("/")
    enter = content_security_policy("/enter/")
    assert "script-src 'self';" in home
    assert "script-src 'self' https://telegram.org" in enter
    assert "style-src-attr 'unsafe-inline'" in home
    assert "frame-ancestors 'self' https://telegram.org https://*.telegram.org" in home
    assert "default-src 'self'" in home
