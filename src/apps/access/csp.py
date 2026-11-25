"""Политика содержимого: свои файлы, скрипт Telegram только на входе."""


def content_security_policy(path: str) -> str:
    """Собирает заголовок. telegram.org разрешён только странице входа."""
    script = "script-src 'self'"
    if path.startswith("/enter"):
        script = "script-src 'self' https://telegram.org"
    return "; ".join(
        [
            "default-src 'self'",
            script,
            "style-src 'self'",
            "style-src-attr 'unsafe-inline'",
            "img-src 'self' data:",
            "font-src 'self'",
            "connect-src 'self'",
            "frame-ancestors 'self' https://telegram.org https://*.telegram.org",
            "base-uri 'self'",
            "form-action 'self'",
            "object-src 'none'",
        ]
    )


class ContentSecurityPolicyMiddleware:
    """Ставит CSP на каждый ответ. Чужие скрипты и встраивание страниц ограничены."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Content-Security-Policy"] = content_security_policy(request.path)
        return response
