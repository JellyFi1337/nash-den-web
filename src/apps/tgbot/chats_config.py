"""Чтение chats.toml. Ошибки файла не останавливают сбор сообщений."""

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

from apps.journal.models import Chat, Topic

LEGACY_CHATS_MESSAGE = "Перенесите chats.toml в папку private/"

_TOP_FIELDS = {"version", "chats", "people"}
_CHAT_FIELDS = {"id", "name", "topics"}
_TOPIC_FIELDS = {"thread_id", "name", "file", "role", "export", "ai"}
_ROLES = {"", "journal", "project", "task"}
_FILE_NAME = re.compile(r"[A-Za-z0-9_-]+")


@dataclass(frozen=True)
class TopicConfig:
    chat_id: int
    thread_id: int
    name: str
    file: str
    role: str
    export: bool
    ai: bool


@dataclass(frozen=True)
class ChatConfig:
    chat_id: int
    name: str
    topics: tuple[TopicConfig, ...]


@dataclass
class ChatsFile:
    chats: tuple[ChatConfig, ...] = ()
    people: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    # Файла нет совсем: бот не в группе, темы не настроены. Это не поломка файла.
    missing: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors


def load_chats_config(path: Path | None = None) -> ChatsFile:
    """Читает файл при каждом вызове. Нет файла или он с ошибками — это список ошибок."""
    source = path if path is not None else _configured_path()
    if source is None:
        return ChatsFile(errors=["Не задан путь CHATS_CONFIG."], missing=True)
    if not source.is_file():
        return ChatsFile(errors=[f"Файл конфигурации не найден: {source}"], missing=True)
    try:
        data = tomllib.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        return ChatsFile(errors=[f"Файл конфигурации не разбирается: {exc}"])
    if not isinstance(data, dict):
        return ChatsFile(errors=["Файл конфигурации должен быть таблицей."])
    return _validate(data)


def apply_chats_config() -> dict:
    """Переносит роли тем из файла в базу. Темы, которых бот ещё не видел, создаются."""
    notice = legacy_chats_message()
    loaded = load_chats_config()
    summary = {
        "updated": 0,
        "created": 0,
        "reset": 0,
        "errors": list(loaded.errors),
        "notice": notice,
    }
    if loaded.errors:
        return summary
    seen: set[tuple[int, int]] = set()
    for chat in loaded.chats:
        chat_row, _created = Chat.objects.get_or_create(
            chat_id=chat.chat_id,
            defaults={"title": chat.name, "is_forum": True},
        )
        if chat.name and chat_row.title != chat.name:
            chat_row.title = chat.name
            chat_row.save(update_fields=["title", "updated_at"])
        for topic in chat.topics:
            row = Topic.objects.filter(chat=chat_row, thread_id=topic.thread_id).first()
            if row is None:
                Topic.objects.create(
                    chat=chat_row,
                    thread_id=topic.thread_id,
                    name=topic.name or f"тема {topic.thread_id}",
                    role=topic.role,
                )
                summary["created"] += 1
            else:
                changed = False
                if row.role != topic.role:
                    row.role = topic.role
                    changed = True
                if topic.name and row.name != topic.name:
                    row.name = topic.name
                    changed = True
                if changed:
                    row.save(update_fields=["role", "name", "updated_at"])
                    summary["updated"] += 1
            seen.add((chat.chat_id, topic.thread_id))
    for topic in Topic.objects.exclude(role="").select_related("chat"):
        if (topic.chat.chat_id, topic.thread_id) in seen:
            continue
        topic.role = ""
        topic.save(update_fields=["role", "updated_at"])
        summary["reset"] += 1
    return summary


def legacy_chats_message() -> str:
    for path in _legacy_paths():
        if path.is_file():
            return LEGACY_CHATS_MESSAGE
    return ""


def _legacy_paths() -> list[Path]:
    root = Path(settings.BASE_DIR).parent
    return [root / "chats.toml", Path("/app/chats.toml")]


def _configured_path() -> Path | None:
    raw = str(settings.CHATS_CONFIG).strip()
    if not raw:
        return None
    return Path(raw)


def _validate(data: dict) -> ChatsFile:
    errors: list[str] = []
    for key in data:
        if key not in _TOP_FIELDS:
            errors.append(f"Неизвестное поле «{key}».")
    version = data.get("version", 1)
    if version != 1:
        errors.append(f"Неизвестная версия файла: {version}.")
    chats, chat_errors = _chats(data.get("chats", []))
    errors.extend(chat_errors)
    people, people_errors = _people(data.get("people", {}))
    errors.extend(people_errors)
    errors.extend(_topic_rules(chats))
    return ChatsFile(chats=tuple(chats), people=people, errors=errors)


def _chats(raw: object) -> tuple[list[ChatConfig], list[str]]:
    if not isinstance(raw, list):
        return [], ["Раздел chats должен быть списком."]
    chats: list[ChatConfig] = []
    errors: list[str] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            errors.append(f"Чат {index} записан не таблицей.")
            continue
        for key in item:
            if key not in _CHAT_FIELDS:
                errors.append(f"Неизвестное поле «{key}» у чата {index}.")
        chat_id = item.get("id")
        name = item.get("name")
        if not isinstance(chat_id, int) or isinstance(chat_id, bool):
            errors.append(f"У чата {index} нет числового id.")
            continue
        if not isinstance(name, str) or not name.strip():
            errors.append(f"У чата {chat_id} нет названия.")
            name = ""
        topics, topic_errors = _topics(chat_id, item.get("topics", []))
        errors.extend(topic_errors)
        chats.append(ChatConfig(chat_id=chat_id, name=name.strip(), topics=tuple(topics)))
    return chats, errors


def _topics(chat_id: int, raw: object) -> tuple[list[TopicConfig], list[str]]:
    if not isinstance(raw, list):
        return [], [f"Темы чата {chat_id} должны быть списком."]
    topics: list[TopicConfig] = []
    errors: list[str] = []
    seen: set[int] = set()
    for item in raw:
        if not isinstance(item, dict):
            errors.append(f"Тема чата {chat_id} записана не таблицей.")
            continue
        for key in item:
            if key not in _TOPIC_FIELDS:
                errors.append(f"Неизвестное поле «{key}» у темы чата {chat_id}.")
        thread_id = item.get("thread_id")
        if not isinstance(thread_id, int) or isinstance(thread_id, bool):
            errors.append(f"У темы чата {chat_id} нет номера thread_id.")
            continue
        if thread_id in seen:
            errors.append(f"Тема {thread_id} в чате {chat_id} указана дважды.")
        seen.add(thread_id)
        name = item.get("name")
        file_name = item.get("file")
        role = item.get("role", "")
        export = item.get("export")
        ai = item.get("ai")
        if not isinstance(name, str):
            errors.append(f"У темы {thread_id} чата {chat_id} нет названия.")
            name = ""
        if not isinstance(file_name, str) or _FILE_NAME.fullmatch(file_name) is None:
            errors.append(
                f"Имя файла темы {thread_id} чата {chat_id} должно быть латиницей без расширения.",
            )
            file_name = ""
        if not isinstance(role, str) or role not in _ROLES:
            errors.append(f"Неизвестная роль «{role}» у темы {thread_id} чата {chat_id}.")
            role = ""
        if not isinstance(export, bool) or not isinstance(ai, bool):
            errors.append(
                f"У темы {thread_id} чата {chat_id} поля export и ai должны быть да или нет.",
            )
            export = bool(export) if isinstance(export, bool) else False
            ai = bool(ai) if isinstance(ai, bool) else False
        topics.append(
            TopicConfig(
                chat_id=chat_id,
                thread_id=thread_id,
                name=name.strip(),
                file=file_name,
                role=role,
                export=export,
                ai=ai,
            ),
        )
    return topics, errors


def _people(raw: object) -> tuple[dict[str, str], list[str]]:
    if raw is None:
        return {}, []
    if not isinstance(raw, dict):
        return {}, ["Раздел people должен быть таблицей."]
    people: dict[str, str] = {}
    errors: list[str] = []
    for key, value in raw.items():
        cleaned = str(key).strip().lstrip("@").lower()
        if not cleaned:
            errors.append("Пустой ключ в разделе people.")
            continue
        if cleaned in people:
            errors.append(f"Ключ человека «{cleaned}» повторяется.")
        if not isinstance(value, str) or not value.strip():
            errors.append(f"У человека «{cleaned}» нет имени.")
            continue
        people[cleaned] = value.strip()
    return people, errors


def _topic_rules(chats: list[ChatConfig]) -> list[str]:
    errors: list[str] = []
    files: dict[str, int] = {}
    journal = 0
    for chat in chats:
        for topic in chat.topics:
            if topic.file:
                files[topic.file] = files.get(topic.file, 0) + 1
            if topic.role == "journal":
                journal += 1
    for file_name, count in files.items():
        if count > 1:
            errors.append(f"Имя файла «{file_name}» повторяется.")
    if journal > 1:
        errors.append("Роль journal указана больше чем у одной темы.")
    return errors
