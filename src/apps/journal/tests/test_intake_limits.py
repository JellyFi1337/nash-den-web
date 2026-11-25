"""Архив отчёта не распаковывается без предела и не роняет процесс."""

import io
import zipfile

from apps.journal.report.intake import ingest_texts, texts_from_bytes


def _zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def test_archive_with_too_many_files_is_rejected() -> None:
    files = {f"{index}.json": b"{}" for index in range(21)}
    lines, ready = ingest_texts(
        texts_from_bytes("pack.zip", _zip(files)),
        via="command",
        publish=False,
    )
    assert ready == []
    assert lines == ["Часть отклонена. В архиве больше 20 файлов."]


def test_archive_bomb_is_rejected_before_it_is_unpacked() -> None:
    payload = _zip({"huge.json": b"0" * (5 * 1024 * 1024 + 1)})
    lines, ready = ingest_texts(texts_from_bytes("bomb.zip", payload), via="command", publish=False)
    assert ready == []
    assert lines == ["Часть отклонена. Архив слишком большой."]


def test_non_utf8_is_a_part_error() -> None:
    lines, ready = ingest_texts(
        texts_from_bytes("part.json", b"\xff\xfe not utf-8"),
        via="command",
        publish=False,
    )
    assert ready == []
    assert lines == ["Часть отклонена. Файл не в кодировке UTF-8."]
    packed = _zip({"part.json": b"\xff"})
    again, days = ingest_texts(texts_from_bytes("pack.zip", packed), via="command", publish=False)
    assert days == []
    assert "UTF-8" in again[0]
    assert "отклонена" in again[0]


def test_valid_archive_still_reaches_the_parser() -> None:
    payload = _zip({"note.txt": "это не json".encode()})
    lines, ready = ingest_texts(texts_from_bytes("pack.zip", payload), via="command", publish=False)
    assert ready == []
    assert lines == ["Это не JSON."]
