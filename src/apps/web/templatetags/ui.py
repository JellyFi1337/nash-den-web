"""Компоненты страниц. Принимают готовые строки и ничего не считают."""

from django import template

from apps.web.typography import typograph

register = template.Library()


@register.filter(name="typo")
def typo(value: object) -> str:
    """Типограф. Обычная строка: автоэкранирование шаблона остаётся."""
    if value is None:
        return ""
    return typograph(str(value))


_STATUS = {
    "done": "is-done",
    "morning": "is-morning",
    "wait": "is-wait",
    "plain": "",
}
_SIZE = {"sm": "avatar--sm", "lg": "avatar--lg"}
_BAR = {"goals": "bar--goals", "lime": "bar--lime"}
_CHIP = {"fill": "chip--fill", "lime": "chip--lime", "hot": "chip--hot"}
_DELTA = {"up": "delta--up", "down": "delta--down", "same": "delta--same"}


@register.inclusion_tag("components/avatar.html")
def avatar(
    letter: str,
    status: str = "wait",
    size: str = "",
    photo: str = "",
    face: str = "",
) -> dict[str, str]:
    return {
        "letter": letter,
        "photo": photo,
        "face": face,
        "status_class": _STATUS.get(status, "is-wait"),
        "size_class": _SIZE.get(size, ""),
    }


@register.inclusion_tag("components/faces.html")
def faces(people: list[dict[str, str]]) -> dict[str, object]:
    return {"people": people}


@register.inclusion_tag("components/bar.html")
def bar(value: str, kind: str = "") -> dict[str, str]:
    return {"value": value, "kind_class": _BAR.get(kind, "")}


@register.inclusion_tag("components/chip.html")
def chip(text: str, kind: str = "", url: str = "") -> dict[str, str]:
    return {"text": text, "url": url, "kind_class": _CHIP.get(kind, "")}


@register.inclusion_tag("components/person.html")
def person(
    name: str,
    letter: str,
    status: str = "wait",
    meta: str = "",
    photo: str = "",
    url: str = "",
    wait: str = "",
    words: str = "",
    scales: list[dict[str, str]] | None = None,
    as_card: bool = False,
    slug: str = "",
    badge: bool = False,
) -> dict[str, object]:
    return {
        "name": name,
        "letter": letter,
        "status": status,
        "meta": meta,
        "photo": photo,
        "url": url or "#",
        "wait": wait,
        "words": words,
        "scales": scales or [],
        "as_card": as_card,
        "slug": slug,
        "badge": badge,
    }


@register.inclusion_tag("components/delta.html")
def delta(direction: str, text: str = "") -> dict[str, str]:
    return {"direction_class": _DELTA.get(direction, "delta--same"), "text": text}


@register.inclusion_tag("components/empty.html")
def empty_state(text: str) -> dict[str, str]:
    return {"text": text}
