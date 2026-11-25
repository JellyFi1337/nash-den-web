"""Адреса входа и закрытых файлов."""

from django.urls import path

from apps.access.views import enter, enter_telegram, leave, logo, media, robots

urlpatterns = [
    path("enter/", enter, name="enter"),
    path("enter/telegram/", enter_telegram, name="enter-telegram"),
    path("exit/", leave, name="exit"),
    path("robots.txt", robots, name="robots"),
    path("logo/", logo, name="logo"),
    path("media/<path:path>", media, name="media"),
]
