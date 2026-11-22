from django.contrib import admin
from django.urls import include, path

from apps.accounts.views import home
from apps.core.views import health

urlpatterns = [
    path("", home, name="home"),
    path("", include("apps.accounts.urls")),
    path("fees/", include("apps.fees.urls")),
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
]
