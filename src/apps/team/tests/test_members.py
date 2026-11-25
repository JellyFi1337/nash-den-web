from io import BytesIO

import pytest
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from PIL import Image

from apps.factories import GoalFactory, MemberFactory
from apps.team.models import Member
from apps.team.slugs import transliterate


def test_transliterate_russian_names() -> None:
    assert transliterate("Ася") == "asya"
    assert transliterate("Семён") == "semyon"


@pytest.mark.django_db
def test_slug_is_latin_and_gets_a_suffix() -> None:
    first = Member.objects.create(full_name="Ася Лебедева", short_name="Ася")
    assert first.slug == "asya"
    semyon = Member.objects.create(full_name="Семён Огарёв", short_name="Семён")
    assert semyon.slug == "semyon"
    second = Member(full_name="Ася Вторая", short_name="Ася2", slug="asya")
    second.save()
    assert second.slug == "asya-2"


@pytest.mark.django_db
def test_telegram_id_accepts_a_large_value() -> None:
    member = MemberFactory(telegram_id=7_000_000_000)
    member.refresh_from_db()
    assert member.telegram_id == 7_000_000_000


@pytest.mark.django_db
def test_short_name_is_unique() -> None:
    MemberFactory(short_name="Лада")
    with pytest.raises(IntegrityError), transaction.atomic():
        MemberFactory(short_name="Лада")


@pytest.mark.django_db
def test_member_with_goal_is_protected() -> None:
    member = MemberFactory()
    GoalFactory(member=member)
    with pytest.raises(ProtectedError):
        member.delete()


@pytest.mark.django_db
def test_photo_is_shrunk_to_jpeg(tmp_path, settings) -> None:
    settings.MEDIA_ROOT = tmp_path
    member = Member(full_name="Нина Ершова", short_name="НинаФото")
    buffer = BytesIO()
    Image.new("RGB", (1000, 400), "red").save(buffer, format="PNG")
    member.photo = ContentFile(buffer.getvalue(), name="face.png")
    member.save()
    with Image.open(member.photo.path) as image:
        assert image.format == "JPEG"
        assert max(image.size) == 640


@pytest.mark.django_db
def test_photo_of_another_format_is_not_opened(tmp_path, settings) -> None:
    settings.MEDIA_ROOT = tmp_path
    member = Member(full_name="Нина Ершова", short_name="НинаГиф")
    buffer = BytesIO()
    Image.new("RGB", (32, 32), "blue").save(buffer, format="GIF")
    member.photo = ContentFile(buffer.getvalue(), name="face.gif")
    member.save()
    with Image.open(member.photo.path) as image:
        assert image.format == "GIF"
