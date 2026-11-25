"""Миниатюры, пустые состояния и разметка без повторных имён переходов."""

from datetime import date

import pytest
from django.template.loader import render_to_string

from apps.access.services import get_current_code
from apps.core.config import get_config
from apps.factories import MemberFactory
from apps.web.typography import typograph


def test_scene_previews_and_settings_choices() -> None:
    body = render_to_string("components/prefs.html")
    assert body.count('class="scene-preview"') == 5
    for scene in ("auto", "morning", "day", "evening", "night"):
        assert f'data-scene-preview="{scene}"' in body
        assert f'name="scene" value="{scene}"' in body
    for kind in ("motion", "bg", "palette", "scale", "comets", "spot", "sparks", "theme"):
        assert f'name="{kind}"' in body
    assert "data-prefs-handle" in body
    assert "data-prefs-auto-caption" in body
    assert 'data-prefs-note="economy"' in body


def test_empty_horizon_is_decorative_and_keeps_the_text() -> None:
    text = "Здесь появятся наши общие достижения — шаги, которые хочется сохранить."
    body = render_to_string("components/empty.html", {"text": text})
    assert 'class="empty__art"' in body
    assert 'aria-hidden="true"' in body
    assert "<path" in body
    assert typograph(text) in body
    assert "brand/" not in body
    unsafe = render_to_string("components/empty.html", {"text": "<script>тест</script>"})
    assert "&lt;script&gt;" in unsafe


@pytest.mark.django_db
def test_person_faces_and_header_have_no_static_transition_names(client) -> None:
    member = MemberFactory(full_name="Лада Демина", short_name="Лада")
    client.post("/enter/", {"code": get_current_code().code})
    for path in ("/", "/team/", f"/team/{member.slug}/"):
        body = client.get(path).content.decode()
        assert "view-transition-name:" not in body
        assert "member-transition.js" in body
        assert 'blocking="render"' in body
    header = client.get(f"/team/{member.slug}/").content.decode()
    assert f'data-member-header="{member.slug}"' in header
    assert "data-member-name" in header
    faces = render_to_string(
        "components/faces.html",
        {
            "people": [
                {"url": f"/team/{member.slug}/", "name": "Лада", "id": member.pk, "letter": "Л"},
                {"url": f"/team/{member.slug}/", "name": "Лада", "id": member.pk, "letter": "Л"},
            ]
        },
    )
    assert faces.count("data-person-link") == 2
    assert "view-transition-name" not in faces


@pytest.mark.parametrize("outside", [False, True])
@pytest.mark.django_db
def test_empty_pages_without_snapshot_keep_settings_and_horizon(client, outside) -> None:
    if outside:
        config = get_config()
        config.stream_start = date(2099, 1, 1)
        config.stream_end = date(2099, 2, 1)
        config.save()
    client.post("/enter/", {"code": get_current_code().code})
    for path in ("/", "/team/", "/stats/", "/days/all/", "/project/"):
        response = client.get(path)
        assert response.status_code == 200
        body = response.content.decode()
        assert body.count('class="scene-preview"') == 5
        assert "data-empty-art" in body
        assert 'aria-hidden="true"' in body
