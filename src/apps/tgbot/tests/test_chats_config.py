"""Конфигурация чатов: верный файл и ошибки."""

from pathlib import Path

from django.test import override_settings

from apps.tgbot.chats_config import load_chats_config

_VALID = """
version = 1

[[chats]]
id = -1001
name = "Вымышленный чат"

  [[chats.topics]]
  thread_id = 0
  name = "General"
  file = "general"
  role = ""
  export = true
  ai = false

  [[chats.topics]]
  thread_id = 2
  name = "Журнал"
  file = "zhurnal"
  role = "journal"
  export = true
  ai = true

[people]
ivan_t = "Тестов Иван"
"""


def test_valid_config_reads_topics_and_people(tmp_path: Path) -> None:
    path = tmp_path / "chats.toml"
    path.write_text(_VALID, encoding="utf-8")
    with override_settings(CHATS_CONFIG=str(path)):
        loaded = load_chats_config()
    assert loaded.ok
    assert loaded.chats[0].topics[1].role == "journal"
    assert loaded.people["ivan_t"] == "Тестов Иван"


def test_unknown_field_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "chats.toml"
    path.write_text('note = "лишнее"\n' + _VALID, encoding="utf-8")
    loaded = load_chats_config(path)
    assert any("Неизвестное поле" in error for error in loaded.errors)


def test_two_journal_topics_are_reported(tmp_path: Path) -> None:
    path = tmp_path / "chats.toml"
    path.write_text(
        """
version = 1

[[chats]]
id = -1001
name = "Чат"

  [[chats.topics]]
  thread_id = 2
  name = "Журнал"
  file = "zhurnal"
  role = "journal"
  export = true
  ai = true

  [[chats.topics]]
  thread_id = 3
  name = "Ещё"
  file = "esche"
  role = "journal"
  export = true
  ai = false

[people]
""",
        encoding="utf-8",
    )
    loaded = load_chats_config(path)
    assert any("journal" in error for error in loaded.errors)


def test_missing_file_does_not_raise(tmp_path: Path) -> None:
    loaded = load_chats_config(tmp_path / "missing.toml")
    assert loaded.errors
    assert loaded.chats == ()
