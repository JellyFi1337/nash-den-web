"""Латинский адрес страницы человека."""

from django.utils.text import slugify

_CYRILLIC = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def transliterate(value: str) -> str:
    """Кириллица в латиницу. Остальные символы не меняются."""
    return "".join(_CYRILLIC.get(char, char) for char in value.lower())


def ensure_slug(member) -> None:
    """Заполняет slug латиницей. Если такой уже есть — добавляет суффикс -2, -3, …"""
    from apps.team.models import Member

    raw = member.slug or member.short_name or member.full_name
    base = slugify(transliterate(raw)) or "member"
    candidate = base
    suffix = 2
    taken = Member.objects.all()
    if member.pk:
        taken = taken.exclude(pk=member.pk)
    while taken.filter(slug=candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    member.slug = candidate
