"""Проверка живого сайта. Код дня не создаёт и в вывод не попадает."""

import argparse
import re
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from urllib.parse import urlsplit

BASE = "http://127.0.0.1:8000"
_EMPTY = "smoke: данных нет, проверены вход и пустые состояния"
_ATTEMPT = "smoke: оставлена попытка входа"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        default="http://127.0.0.1:8000",
        help="Адрес сайта, например https://den.example или http://127.0.0.1:8080.",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Не создавать код дня. Так команда работает и без этого ключа.",
    )
    args = parser.parse_args([] if argv is None else argv)
    global BASE
    BASE = args.base.rstrip("/")
    https = BASE.startswith("https://")
    import django

    django.setup()
    from apps.access.models import DayCode
    from apps.core.time import site_day
    from apps.team.models import Member

    code = DayCode.objects.filter(day=site_day()).first()
    has_people = Member.objects.exists()
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    if https:
        _check_https_redirect(BASE)

    health = _read(opener, "/health/")
    _expect(health, 200, "здоровье")
    if b'"status": "ok"' not in health.body and b'"status":"ok"' not in health.body:
        _fail("здоровье не подтвердило базу")

    enter = _read(opener, "/enter/")
    _expect(enter, 200, "страница входа")
    _check_headers(enter, https=https)
    if code is None:
        if has_people:
            _fail("кода дня нет, новый не создаю")
        print(_EMPTY)
        print("smoke: код дня не создавался, попытка входа не записана")
        return

    token = _csrf(enter.body)
    posted = _read(
        opener,
        "/enter/",
        data=f"code={_quote(code.code)}&csrfmiddlewaretoken={_quote(token)}".encode(),
        headers={"Referer": BASE + "/enter/", "X-CSRFToken": token},
    )
    if posted.status not in {200, 302}:
        _fail(f"вход ответил {posted.status}")
    if posted.status == 200 and "Код не подош" in posted.body.decode("utf-8", "replace"):
        _fail("код дня не принят")
    print(_ATTEMPT)

    home = _read(opener, "/")
    _expect(home, 200, "главная")
    day = _read(opener, f"/days/{site_day().isoformat()}/")
    _expect(day, 200, "день")
    team = _read(opener, "/team/")
    _expect(team, 200, "команда")
    team_html = team.body.decode("utf-8", "replace")
    match = re.search(r'href="(/team/[^"]+/)"', team_html)
    if match is None:
        if "Ещё тихо" not in team_html:
            _fail("пустая команда без пояснения")
        print(_EMPTY)
        return
    person = _read(opener, match.group(1))
    _expect(person, 200, "человек")
    _expect(_read(opener, "/project/"), 200, "проект")
    _expect(_read(opener, "/stats/"), 200, "статистика")
    pulse = _read(opener, "/api/pulse/", headers={"Accept": "application/json"})
    _expect(pulse, 200, "пульс")
    if b'"morning"' not in pulse.body:
        _fail("пульс без данных")
    missing = _read(opener, "/net-takoy-stranicy/")
    _expect(missing, 404, "несуществующая страница")
    print("smoke: ok")


class _Page:
    def __init__(self, status: int, body: bytes, headers) -> None:
        self.status = status
        self.body = body
        self.headers = headers


class _NoRedirect(urllib.request.HTTPErrorProcessor):
    """Оставляет ответ 30x как есть, чтобы увидеть переход на HTTPS."""

    def http_response(self, request, response):
        return response

    https_response = http_response


def _read(opener, path: str, *, data: bytes | None = None, headers: dict | None = None) -> _Page:
    request = urllib.request.Request(BASE + path, data=data, headers=headers or {})
    try:
        with opener.open(request, timeout=20) as response:
            return _Page(response.status, response.read(), response.headers)
    except urllib.error.HTTPError as exc:
        return _Page(exc.code, exc.read(), exc.headers)
    except urllib.error.URLError as exc:
        _fail(f"не открылся {path}: {exc.reason}")


def _check_https_redirect(base: str) -> None:
    host = urlsplit(base).netloc
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(f"http://{host}/")
    try:
        with opener.open(request, timeout=20) as response:
            status = response.status
            location = response.headers.get("Location") or ""
    except urllib.error.HTTPError as exc:
        status = exc.code
        location = exc.headers.get("Location") or ""
    except urllib.error.URLError as exc:
        _fail(f"HTTP не открылся: {exc.reason}")
    if status not in {301, 302, 307, 308} or not location.startswith("https://"):
        _fail("HTTP не переходит на HTTPS")


def _check_headers(page: _Page, *, https: bool) -> None:
    policy = page.headers.get("Content-Security-Policy") or ""
    if "default-src" not in policy or "frame-ancestors" not in policy:
        _fail("нет политики содержимого")
    hsts = page.headers.get("Strict-Transport-Security") or ""
    if hsts and "max-age=" not in hsts.lower():
        _fail("заголовок HSTS без срока")
    if not https:
        return
    cookies = page.headers.get_all("Set-Cookie") if page.headers else None
    if not cookies or not any("secure" in item.lower() for item in cookies):
        _fail("cookie без Secure")


def _csrf(body: bytes) -> str:
    match = re.search(
        r'name="csrfmiddlewaretoken" value="([^"]+)"',
        body.decode("utf-8", "replace"),
    )
    if match is None:
        _fail("на странице входа нет токена")
    return match.group(1)


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


def _expect(page: _Page, status: int, name: str) -> None:
    if page.status != status:
        _fail(f"{name}: ожидался ответ {status}, пришёл {page.status}")


def _fail(message: str) -> None:
    print(f"smoke: {message}", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
