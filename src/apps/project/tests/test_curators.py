import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client

from apps.project.curators import ensure_curators

EXPECTED = {
    ("journal", "view_day"),
    ("journal", "change_day"),
    ("journal", "view_timelineevent"),
    ("journal", "change_timelineevent"),
    ("journal", "view_achievement"),
    ("journal", "change_achievement"),
    ("project", "view_project"),
    ("project", "change_project"),
    ("project", "view_checklistitem"),
    ("project", "change_checklistitem"),
    ("project", "view_decision"),
    ("project", "change_decision"),
    ("project", "view_openquestion"),
    ("project", "change_openquestion"),
    ("team", "view_member"),
    ("team", "view_goal"),
    ("journal", "view_entry"),
}
CLOSED = (
    "/dkr-admin/access/daycode/",
    "/dkr-admin/access/loginattempt/",
    "/dkr-admin/team/telegramcontact/",
    "/dkr-admin/core/siteconfig/",
    "/dkr-admin/journal/rawmessage/",
)


@pytest.mark.django_db
def test_curators_have_exactly_the_expected_permissions() -> None:
    group = Group.objects.get(name="Кураторы")
    codes = set(group.permissions.values_list("content_type__app_label", "codename"))
    assert codes == EXPECTED
    ensure_curators()
    again = set(group.permissions.values_list("content_type__app_label", "codename"))
    assert again == EXPECTED
    assert Group.objects.filter(name="Кураторы").count() == 1


@pytest.mark.django_db
def test_curator_cannot_open_closed_admin_lists() -> None:
    user = get_user_model().objects.create_user("curator", password="secret-pass", is_staff=True)
    user.groups.add(Group.objects.get(name="Кураторы"))
    client = Client()
    client.force_login(user)
    assert client.get("/dkr-admin/team/member/").status_code == 200
    for url in CLOSED:
        response = client.get(url)
        if response.status_code == 302:
            response = client.get(response["Location"])
        assert response.status_code == 403, url
