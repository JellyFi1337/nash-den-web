"""Типограф выводимого текста. В базе строки не меняются."""

import re

# Закрытый список: ровно эти слова, не любые из одной-двух букв.
SHORT_WORDS: tuple[str, ...] = (
    "а",
    "в",
    "во",
    "и",
    "к",
    "ко",
    "о",
    "об",
    "обо",
    "от",
    "с",
    "со",
    "у",
    "я",
    "на",
    "по",
    "за",
    "до",
    "из",
    "не",
    "ни",
    "но",
    "да",
    "или",
)

PARTICLES: tuple[str, ...] = ("же", "ли", "бы")

UNITS: tuple[str, ...] = (
    "₽",
    "%",
    "‰",
    "дн.",
    "дня",
    "дней",
    "ч",
    "мин",
    "чел.",
    "человек",
)

NBSP = "\u00a0"

_SHORT_ALT = "|".join(re.escape(word) for word in sorted(SHORT_WORDS, key=len, reverse=True))
_PARTICLE_ALT = "|".join(PARTICLES)
_UNIT_ALT = "|".join(re.escape(unit) for unit in sorted(UNITS, key=len, reverse=True))

# Адрес целиком уходит в заглушку: внутри него пробелы не ставятся.
_PROTECTED = re.compile(
    r"https?://[^\s<>\"']+|www\.[^\s<>\"']+|[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-я]{2,}(?![\w])",
    re.IGNORECASE,
)
_SHORT = re.compile(rf"(?<![\w])(?:{_SHORT_ALT}) (?=\S)", re.IGNORECASE)
_PARTICLE = re.compile(rf" (?=(?:{_PARTICLE_ALT})(?![\w]))", re.IGNORECASE)
_DASH = re.compile(r" (?=[—–])")
_UNIT = re.compile(rf"(?<=\d) ({_UNIT_ALT})(?![\w])", re.IGNORECASE)


def typograph(text: str | None) -> str:
    """Неразрывные пробелы по правилам русской типографики. Повторный вызов ничего не меняет."""
    if not text:
        return ""
    shielded, saved = _shield(text)
    spaced = _SHORT.sub(lambda match: match.group(0)[:-1] + NBSP, shielded)
    spaced = _PARTICLE.sub(NBSP, spaced)
    spaced = _DASH.sub(NBSP, spaced)
    spaced = _UNIT.sub(lambda match: NBSP + match.group(1), spaced)
    return _restore(spaced, saved)


def _shield(text: str) -> tuple[str, list[str]]:
    saved: list[str] = []

    def replace(match: re.Match[str]) -> str:
        saved.append(match.group(0))
        return f"\ue000{len(saved) - 1}\ue001"

    return _PROTECTED.sub(replace, text), saved


def _restore(text: str, saved: list[str]) -> str:
    for index, value in enumerate(saved):
        text = text.replace(f"\ue000{index}\ue001", value)
    return text
