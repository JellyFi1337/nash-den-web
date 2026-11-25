"""Проверка initData мини-приложения Telegram. Сеть не нужна."""

import hashlib
import hmac
import json
from datetime import datetime
from urllib.parse import parse_qsl

MAX_AGE_SECONDS = 24 * 60 * 60


def verify_init_data(raw: str, token: str, moment: datetime) -> dict | None:
    """Подпись по правилам Telegram Web Apps. Старше суток — отказ."""
    if not raw or not token:
        return None
    pairs = dict(parse_qsl(raw, keep_blank_values=True))
    received = pairs.pop("hash", "")
    if not received:
        return None
    check = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, received):
        return None
    try:
        auth_date = int(pairs.get("auth_date") or 0)
    except ValueError:
        return None
    if moment.timestamp() - auth_date > MAX_AGE_SECONDS:
        return None
    try:
        user = json.loads(pairs.get("user") or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(user, dict) or "id" not in user:
        return None
    return user
