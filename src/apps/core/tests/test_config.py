import pytest

from apps.core.code_words import DEFAULT_CODE_WORDS
from apps.core.config import get_config
from apps.core.models import SiteConfig
from apps.project.config import get_project


@pytest.mark.django_db
def test_get_config_creates_once_and_drops_cache_on_save() -> None:
    assert SiteConfig.objects.count() == 0
    first = get_config()
    second = get_config()
    assert first.pk == second.pk == 1
    assert SiteConfig.objects.count() == 1
    assert "ВАЖНО" in first.code_words
    assert len(DEFAULT_CODE_WORDS) >= 40
    first.site_title = "Другое имя"
    first.save()
    assert get_config().site_title == "Другое имя"


@pytest.mark.django_db
def test_get_project_creates_one_row() -> None:
    first = get_project()
    second = get_project()
    assert first.pk == second.pk == 1
