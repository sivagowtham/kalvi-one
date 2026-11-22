import pytest
from django.conf import settings
from django.db import connection


def test_settings_use_postgresql():
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"


def test_time_zone_is_india():
    assert settings.TIME_ZONE == "Asia/Kolkata"


@pytest.mark.django_db
def test_database_is_reachable():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)


@pytest.mark.django_db
def test_health_endpoint_returns_ok(client):
    response = client.get("/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_health_endpoint_rejects_post(client):
    response = client.post("/health/")
    assert response.status_code == 405
