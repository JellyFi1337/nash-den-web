from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.template import Context, Template
from django.test import RequestFactory, override_settings
from django.urls import resolve

from apps.access.services import get_current_code
from apps.core.config import get_config
from apps.core.time import stream_day_number, stream_length
from apps.web.context import shell
from apps.web.typography import typograph

MOSCOW = ZoneInfo("Europe/Moscow")


def _request(path: str):
    request = RequestFactory().get(path)
    request.resolver_match = resolve(path)
    return request


@pytest.mark.django_db
def test_shell_inside_the_stream_and_without_a_logo() -> None:
    moment = datetime(2026, 9, 29, 12, 0, tzinfo=MOSCOW)
    with time_machine.travel(moment, tick=False):
        data = shell(_request("/"))["shell"]
    assert data["date_label"] == "ВТ 29.09"
    assert stream_length() == 63
    assert stream_day_number(date(2026, 9, 29)) == 9
    assert data["stream_chip"] == "ступень 3 · день 04"
    assert data["in_stream"] is True
    assert data["logo_url"] == ""
    assert data["section"] == "today"
    assert data["brand"] == "НАШ ДЕНЬ"


@pytest.mark.django_db
def test_shell_hides_the_stream_chip_outside_the_stream() -> None:
    config = get_config()
    config.stream_start = config.stream_start.replace(year=2030)
    config.stream_end = config.stream_end.replace(year=2030)
    config.save()
    moment = datetime(2026, 9, 29, 12, 0, tzinfo=MOSCOW)
    with time_machine.travel(moment, tick=False):
        data = shell(_request("/team/"))["shell"]
    assert data["in_stream"] is False
    assert data["stream_chip"] == ""
    assert data["section"] == "team"


def test_template_tags_render_ready_data() -> None:
    html = Template(
        "{% load ui %}"
        "{% avatar letter='Л' status='done' %}"
        "{% bar value='80%' kind='goals' %}"
        "{% chip text='день 09/63' kind='fill' %}"
        "{% delta direction='up' text='50' %}"
        "{% empty_state 'Ещё тихо. Первая запись откроет день.' %}"
    ).render(Context({}))
    assert 'class="avatar  is-done"' in html
    assert ">Л<" in html
    assert 'class="bar bar--goals"' in html
    assert "--v:80%" in html
    assert "chip--fill" in html
    assert "день 09/63" in html
    assert "delta--up" in html
    assert "Ещё тихо" in html


@pytest.mark.django_db
def test_ui_page_is_hidden_without_debug(client) -> None:
    client.post("/enter/", {"code": get_current_code().code})
    response = client.get("/_ui/")
    assert response.status_code == 404
    assert "Такой страницы нет." in response.content.decode()


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_ui_page_is_open_in_debug(client) -> None:
    client.post("/enter/", {"code": get_current_code().code})
    response = client.get("/_ui/")
    assert response.status_code == 200
    assert "пульс дня" in response.content.decode()
    assert "nav-float" in response.content.decode()


@pytest.mark.django_db
def test_stage_day_counts_from_the_start_of_the_third_stage() -> None:
    from apps.web.stage import stage_info

    info = stage_info(date(2026, 10, 2))
    assert info["day"] == 7
    assert info["stage"] == 3
    assert info["last"] is True
    assert info["spoken"] == "7-й день 3-й ступени (последней)"
    assert stage_info(date(2026, 9, 26))["day"] == 1
    assert stage_info(date(2026, 9, 25)) is None
    assert stage_info(date(2026, 11, 23)) is None


@pytest.mark.django_db
def test_home_about_names_the_team_and_counts_curators_in() -> None:
    from django.test import Client

    from apps.access.services import get_current_code
    from apps.factories import MemberFactory
    from apps.team.models import Member

    MemberFactory(short_name="Участник")
    MemberFactory(short_name="Куратор", role=Member.Role.CURATOR)
    client = Client()
    with time_machine.travel(datetime(2026, 10, 2, 12, 0, tzinfo=MOSCOW), tick=False):
        client.post("/enter/", {"code": get_current_code().code})
        home = client.get("/").content.decode()
    about = home.split("b-about", 1)[1].split("</section>", 1)[0]
    assert "«Мир возможностей» · 9 поток" in about
    assert typograph("1 участников и 1 кураторов — одна команда") in about
    assert "день 3-й ступени" in about
    assert typograph("3-я ступень, последняя · 26.09 — 22.11") in about
