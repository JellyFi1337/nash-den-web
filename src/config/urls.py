"""Корневые адреса."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.core.views import health

urlpatterns = [
    path(settings.ADMIN_PATH, admin.site.urls),
    path("", include("apps.access.urls")),
    path("", include("apps.web.urls")),
    path("health/", health, name="health"),
]

handler403 = "apps.web.views.forbidden"
handler404 = "apps.web.views.not_found"
handler500 = "apps.web.views.server_error"
