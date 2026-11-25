"""Вымышленные демо-данные тем же путём, что и настоящие: сообщения, затем отчёт."""

import random
from datetime import datetime, timedelta

from django.utils import timezone

from apps.core.time import now, site_day
from apps.journal.models import Achievement, Chat, Topic
from apps.journal.report.service import accept_part, publish_report
from apps.journal.services import IncomingMessage, ensure_day, store_message
from apps.project.config import get_project
from apps.project.models import ChecklistItem, Decision, OpenQuestion
from apps.team.models import Goal, Member

PARTICIPANTS = (
    ("Ася", "Лебедева", "asya_l"),
    ("Борис", "Кротов", "boris_k"),
    ("Вера", "Шишкина", "vera_sh"),
    ("Глеб", "Морозов", "gleb_m"),
    ("Дина", "Белова", "dina_b"),
    ("Егор", "Сафонов", "egor_s"),
    ("Жанна", "Ильина", "zhanna_i"),
    ("Захар", "Пчёлкин", "zahar_p"),
    ("Инна", "Воронина", "inna_v"),
    ("Кира", "Солнцева", "kira_s"),
    ("Лада", "Черных", "lada_ch"),
    ("Марк", "Дудин", "mark_d"),
    ("Нина", "Ершова", "nina_e"),
    ("Олег", "Баранов", "oleg_b"),
)
CURATORS = (
    ("Павел", "Ремезов", "pavel_r"),
    ("Рита", "Князева", "rita_k"),
    ("Семён", "Огарёв", "semen_o"),
    ("Тая", "Брусникина", "taya_b"),
    ("Ульяна", "Демина", "ulyana_d"),
)
GOALS = (
    (Goal.Kind.BREAKTHROUGH, "Собрать своё утро и не бросать его"),
    (Goal.Kind.CREATIVE, "Сделать одну работу для общего города"),
    (Goal.Kind.UNFINISHED, "Закрыть старый хвост, который тянется с прошлого"),
)
TOPICS = (
    (0, "General", "general", ""),
    (12, "Контексты/Итоги", "konteksty-itogi", "journal"),
    (14, "Инсайты по заданиям", "insayty", "task"),
    (16, "ОП", "op", "project"),
    (18, "ОП ЛИДЕРЫ", "op-lidery", "project"),
    (20, "Отдел СМИ", "otdel-smi", "project"),
    (22, "Личные цели", "lichnye-tseli", ""),
    (24, "ЛИДЕРСКИЙ ЧАТ", "liderskiy-chat", ""),
    (26, "Игра осознанности", "igra-osoznannosti", ""),
    (28, "Противосливный кружок", "protivoslivnyy-kruzhok", ""),
    (30, "Лидерский танец", "liderskiy-tanets", ""),
    (32, "Плакаты", "plakaty", ""),
)
MORNINGS = (
    "Сегодня беру один понятный шаг и не распыляюсь на чужие задачи.",
    "Утро тихое: сначала дело, потом разговоры и ничего лишнего.",
    "Держу контекст коротким и не тащу вчерашнее в новый день.",
)
EVENINGS = (
    "День закрыт. Главное сделано, хвост перенесён спокойно и без спешки.",
    "Итог без героизма: двигался и остановился вовремя, этого достаточно.",
    "Вечер короче, чем хотелось, и этого достаточно для честного дня.",
)
CHAT_ID = -100900000001
JOURNAL = 12
SEED = 20260921


def build_demo() -> None:
    """19 человек, девять дней сообщений, восемь опубликованных отчётов."""
    random.seed(SEED)
    today = site_day()
    members = _members()
    _chat()
    _project()
    for offset in range(8, -1, -1):
        day = today - timedelta(days=offset)
        _messages(members, day, today)
        if day < today:
            _report(members, day)
    _week(members, today)


def _members() -> list[Member]:
    rows = []
    people = [(item, Member.Role.PARTICIPANT) for item in PARTICIPANTS]
    people += [(item, Member.Role.CURATOR) for item in CURATORS]
    for index, ((first, last, username), role) in enumerate(people):
        member = Member.objects.create(
            full_name=f"{first} {last}",
            short_name=first,
            role=role,
            telegram_username=username,
            telegram_id=910000 + index,
            is_active=True,
            is_demo=True,
            sort_order=index,
        )
        for order, (kind, title) in enumerate(GOALS):
            Goal.objects.create(member=member, kind=kind, title=title, sort_order=order)
        rows.append(member)
    return rows


def _chat() -> None:
    chat = Chat.objects.create(
        chat_id=CHAT_ID, title="Демо · 9 поток", kind="supergroup", is_forum=True
    )
    for thread_id, name, _file, role in TOPICS:
        Topic.objects.create(chat=chat, thread_id=thread_id, name=name, role=role)


def _project() -> None:
    project = get_project()
    project.title = "Город нового времени"
    project.tagline = "Вымышленный проект демо-потока"
    project.save()
    ChecklistItem.objects.create(title="Собрать площадку", sort_order=1)
    Decision.objects.create(title="Выбрать формат встречи", sort_order=1)
    OpenQuestion.objects.create(text="Кто ведёт следующий созвон?")
    Achievement.objects.create(
        date=site_day() - timedelta(days=2), title="Первый общий текст готов"
    )


def _messages(members: list[Member], day, today) -> None:
    zone = timezone.get_current_timezone()
    moment = now()
    for index, member in enumerate(members):
        morning_at = datetime.combine(day, datetime.min.time(), tzinfo=zone).replace(
            hour=8,
            minute=index % 50,
        )
        if day == today and morning_at > moment:
            continue
        text = MORNINGS[index % len(MORNINGS)]
        if index == 0 and day == today - timedelta(days=3):
            text = "коротко"
        morning_id = _message_id(day, index, 1)
        _store(member, morning_at, text, morning_id, None)
        if index == len(members) - 1 and day == today:
            continue
        if index == 2 and day == today - timedelta(days=4):
            evening_at = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=zone)
            evening_at = evening_at.replace(hour=1, minute=10)
        else:
            evening_at = datetime.combine(day, datetime.min.time(), tzinfo=zone).replace(
                hour=18,
                minute=index % 40,
            )
        if evening_at > moment:
            continue
        reply = morning_id if index % 3 == 0 else None
        _store(
            member, evening_at, EVENINGS[index % len(EVENINGS)], _message_id(day, index, 2), reply
        )


def _store(
    member: Member, sent_at: datetime, text: str, message_id: int, reply: int | None
) -> None:
    store_message(
        IncomingMessage(
            chat_id=CHAT_ID,
            chat_title="Демо · 9 поток",
            chat_kind="supergroup",
            is_forum=True,
            message_id=message_id,
            thread_id=JOURNAL,
            topic_name="Контексты/Итоги",
            sender_tg_id=member.telegram_id or 0,
            sender_username=member.telegram_username,
            sender_name=member.full_name,
            reply_to_message_id=reply,
            text=text,
            content_type="text",
            forward_from="",
            sent_at=sent_at,
            edited_at=None,
        ),
    )


def _report(members: list[Member], day) -> None:
    stamp = day.strftime("%d.%m.%Y")
    people = []
    for index, member in enumerate(members):
        morning = {
            "sent": f"{stamp} {8:02d}:{(index % 50):02d}",
            "context": MORNINGS[index % len(MORNINGS)],
            "goals": ["Один понятный шаг"],
            "callsign": "Маяк" if index % 2 == 0 else "",
        }
        evening = {
            "sent": f"{stamp} {18:02d}:{(index % 40):02d}",
            "context_pct": 70 + (index % 3) * 10,
            "goals_pct": 60 + (index % 4) * 10,
            "text": EVENINGS[index % len(EVENINGS)],
            "highlight": "Тихий ход" if index % 5 == 0 else "",
            "wins": ["Сделал задуманное"],
        }
        people.append({"member": member.telegram_username, "morning": morning, "evening": evening})
    den = {
        "format": "nash-den.report",
        "version": 2,
        "part": "den",
        "day": day.isoformat(),
        "title": "Тихий рабочий день",
        "lead": "Команда держала один общий шаг и не распылялась.",
        "summary": "Утро собралось рано, вечером почти все закрыли день спокойно.",
        "bullets": ["Утро записано", "Итоги без гонки"],
        "weather": {"code": "clear", "text": "ясно"},
        "tempo": "ровный",
        "timeline": [
            {
                "time": "10:00",
                "kind": "start",
                "title": "Общий сбор",
                "text": "Договорились о шаге",
            },
        ],
        "task": {"title": "Один честный шаг", "essence": "Сделать одно дело до конца.", "done": []},
        "chat": (
            f"🎙 Наш день · {day:%d.%m} · Тихий рабочий день\n\n"
            "Утро собралось рано, вечером почти все закрыли день спокойно.\n"
            "🏗 Проект: появился черновик программы.\n"
            "💬 «Сегодня было тихо и ясно.» — Борис"
        ),
    }
    lyudi = {
        "format": "nash-den.report",
        "version": 2,
        "part": "lyudi",
        "day": day.isoformat(),
        "people": people,
    }
    proekt = {
        "format": "nash-den.report",
        "version": 2,
        "part": "proekt",
        "day": day.isoformat(),
        "pulse": "Проект двигается маленькими шагами.",
        "progress": [{"text": "Появился черновик программы", "who": []}],
        "departments": [
            {
                "name": "Отдел СМИ",
                "summary": "Тексты в работе",
                "done": ["Черновик анонса"],
                "next": ["Выбрать визуал"],
                "people": [members[2].telegram_username],
            },
            {
                "name": "Площадка",
                "summary": "Два варианта на выбор",
                "next": ["Съездить и посмотреть"],
                "people": [],
            },
        ],
        "next_step": {"text": "Сверить программу", "owners": []},
    }
    golosa = {
        "format": "nash-den.report",
        "version": 2,
        "part": "golosa",
        "day": day.isoformat(),
        "insights": [
            {"member": members[0].telegram_username, "text": "Маленький шаг держит день."}
        ],
        "voices": [{"member": members[1].telegram_username, "text": "Сегодня было тихо и ясно."}],
        "words": [{"word": "шаг", "count": 4}],
        "light": [{"text": "Команда назвала день ровным", "who": []}],
    }
    svyazi = {
        "format": "nash-den.report",
        "version": 2,
        "part": "svyazi",
        "day": day.isoformat(),
        "links": [
            {
                "from": members[0].telegram_username,
                "to": members[1].telegram_username,
                "kind": "support",
                "text": "Напомнил про один шаг",
            }
        ],
        "pairs": [],
    }
    for part in (den, lyudi, proekt, golosa, svyazi):
        accept_part(day, part["part"], part, via="command")
    from apps.journal.models import DayReport

    publish_report(DayReport.objects.get(day=day))
    ensure_day(day)


def _week(members: list[Member], today) -> None:
    """«Неделя словами» для текущей недели потока, тем же приёмом, что у владельца."""
    from apps.journal.report.week import accept_week, publish_week, validate_week
    from apps.journal.report.week_pack import default_week

    number = default_week()
    if number is None:
        return
    data = {
        "format": "nash-den.week",
        "version": 1,
        "week": number,
        "title": "Неделя маленьких шагов",
        "lead": "Мы держали один общий шаг в день и не распылялись. Утро собиралось рано.",
        "sections": [
            {
                "heading": "Как шла неделя",
                "text": "Каждый день — «Тихий рабочий день»: утро записано, итоги без гонки.",
            },
            {"heading": "Проект", "text": "Появился черновик программы, площадок две."},
        ],
        "voices": [
            {
                "member": members[1].telegram_username,
                "text": "Сегодня было тихо и ясно.",
                "day": (today - timedelta(days=1)).isoformat(),
            },
        ],
        "next": "Выбрать площадку и сверить программу.",
    }
    check = validate_week(data)
    if not check.ok:
        return
    publish_week(accept_week(check.data, warnings=check.warnings, notes=[], via="command"))


def _message_id(day, index: int, kind: int) -> int:
    return int(day.strftime("%m%d")) * 1000 + index * 10 + kind
