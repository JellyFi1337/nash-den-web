"""Адреса страниц сайта."""

from django.urls import path

from apps.web.views import (
    almanac_page,
    day_page,
    days_all_page,
    days_page,
    home,
    member_page,
    project_page,
    pulse,
    search,
    stats_page,
    tasks_page,
    team_page,
    ui_page,
    voices_page,
    week_page,
    weeks_page,
)

urlpatterns = [
    path("", home, name="home"),
    path("api/pulse/", pulse, name="pulse"),
    path("api/search/", search, name="search"),
    path("weeks/", weeks_page, name="weeks"),
    path("weeks/<int:number>/", week_page, name="week"),
    path("almanac/", almanac_page, name="almanac"),
    path("tasks/", tasks_page, name="tasks"),
    path("voices/", voices_page, name="voices"),
    path("team/", team_page, name="team"),
    path("team/<slug:slug>/", member_page, name="member"),
    path("days/", days_page, name="days"),
    path("days/all/", days_all_page, name="days_all"),
    path("days/<str:iso>/", day_page, name="day"),
    path("project/", project_page, name="project"),
    path("stats/", stats_page, name="stats"),
    path("_ui/", ui_page, name="ui"),
]
