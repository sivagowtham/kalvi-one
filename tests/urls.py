"""Test URLconf: the real project URLs plus the test app's views."""

from django.urls import include, path

from config.urls import urlpatterns as project_urlpatterns

urlpatterns = [*project_urlpatterns, path("testapp/", include("tests.testapp.urls"))]
