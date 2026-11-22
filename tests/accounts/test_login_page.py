"""The college login page, logout, password change and the pause after wrong passwords (D23)."""

import pytest
from django.test import override_settings

from apps.accounts.roles import Role
from apps.audit.models import AuditEvent

pytestmark = pytest.mark.django_db

ALPHA = "alpha.localhost"
BETA = "beta.localhost"
PASSWORD = "correct-horse-1"


def login(client, username, password=PASSWORD, host=ALPHA, ip="127.0.0.1", **data):
    return client.post(
        "/login/",
        {"username": username, "password": password, **data},
        HTTP_HOST=host,
        REMOTE_ADDR=ip,
    )


def events(college, action):
    return AuditEvent.all_colleges.filter(college=college, action=action)


def test_login_page_names_the_college(client, college_a):
    page = client.get("/login/", HTTP_HOST=ALPHA)
    assert page.status_code == 200
    assert b"Alpha College of Engineering" in page.content
    assert b"Email or roll number" in page.content


def test_unknown_college_host_has_no_login_page(client, college_a):
    assert client.get("/login/", HTTP_HOST="nowhere.localhost").status_code == 404


def test_staff_log_in_and_land_on_home(client, college_a, make_user):
    make_user(college_a, "teacher@alpha.test", roles=[Role.FACULTY], full_name="Kavya Raman")
    response = login(client, "teacher@alpha.test")
    assert response.status_code == 302
    assert response.url == "/"
    home = client.get("/", HTTP_HOST=ALPHA)
    assert b"Welcome, Kavya" in home.content
    assert b"Faculty" in home.content
    assert events(college_a, AuditEvent.Action.LOGIN).count() == 1


def test_students_log_in_with_roll_number(client, college_a, make_user):
    make_user(college_a, "24CS001", roles=[Role.STUDENT], is_staff=False)
    assert login(client, "24CS001").url == "/"
    home = client.get("/", HTTP_HOST=ALPHA)
    assert b"office workspace" not in home.content


def test_login_follows_safe_next_only(client, college_a, make_user):
    make_user(college_a, "teacher")
    assert login(client, "teacher", next="/password/change/").url == "/password/change/"
    client.logout()
    assert login(client, "teacher", next="https://evil.example/").url == "/"


def test_login_is_refused_on_another_college(client, college_a, college_b, make_user):
    make_user(college_a, "teacher")
    response = login(client, "teacher", host=BETA)
    assert response.status_code == 200
    assert b"do not match" in response.content
    assert events(college_b, AuditEvent.Action.LOGIN_FAILED).count() == 1


def test_account_without_password_cannot_log_in(client, college_a, make_user):
    make_user(college_a, "24CS002", password=None)
    assert login(client, "24CS002", password="").status_code == 200
    assert login(client, "24CS002", password="anything-at-all").status_code == 200


def test_home_needs_login(client, college_a):
    response = client.get("/", HTTP_HOST=ALPHA)
    assert response.status_code == 302
    assert response.url == "/login/?next=/"


def test_signed_in_user_skips_login_page(client, college_a, make_user):
    client.force_login(make_user(college_a, "teacher"))
    assert client.get("/login/", HTTP_HOST=ALPHA).url == "/"


def test_logout_needs_post_and_is_audited(client, college_a, make_user):
    client.force_login(make_user(college_a, "teacher"))
    assert client.get("/logout/", HTTP_HOST=ALPHA).status_code == 405
    response = client.post("/logout/", HTTP_HOST=ALPHA)
    assert response.url == "/login/"
    assert events(college_a, AuditEvent.Action.LOGOUT).count() == 1
    assert client.get("/", HTTP_HOST=ALPHA).status_code == 302


def test_password_change(client, college_a, make_user):
    user = make_user(college_a, "teacher")
    client.force_login(user)
    assert client.get("/password/change/", HTTP_HOST=ALPHA).status_code == 200
    response = client.post(
        "/password/change/",
        {
            "old_password": PASSWORD,
            "new_password1": "a-new-long-pass-42",
            "new_password2": "a-new-long-pass-42",
        },
        HTTP_HOST=ALPHA,
    )
    assert response.url == "/"
    user.refresh_from_db()
    assert user.check_password("a-new-long-pass-42")
    # Still signed in, and the change is in the audit log with the hash masked.
    assert client.get("/", HTTP_HOST=ALPHA).status_code == 200
    update = events(college_a, AuditEvent.Action.UPDATE).filter(object_id=str(user.pk)).last()
    assert update.changes["password"] == ["***", "***"]


def test_password_change_needs_login(client, college_a):
    assert client.get("/password/change/", HTTP_HOST=ALPHA).status_code == 302


@override_settings(LOGIN_FAILURE_LIMIT=3)
def test_login_pauses_after_too_many_wrong_passwords(client, college_a, make_user):
    make_user(college_a, "teacher")
    for _ in range(3):
        login(client, "teacher", password="wrong-password")
    response = login(client, "teacher")  # right password, but paused
    assert response.status_code == 200
    assert b"Too many wrong passwords" in response.content
    refused = events(college_a, AuditEvent.Action.LOGIN_FAILED).filter(
        extra__reason="too_many_attempts"
    )
    assert refused.count() == 1


@override_settings(LOGIN_FAILURE_LIMIT=3)
def test_pause_is_per_college_and_per_ip(client, college_a, college_b, make_user):
    make_user(college_a, "teacher")
    make_user(college_b, "teacher")
    for _ in range(3):
        login(client, "teacher", password="wrong-password")
    assert login(client, "teacher", host=BETA).url == "/"
    client.logout()
    assert login(client, "teacher", ip="10.0.0.9").url == "/"


@override_settings(LOGIN_FAILURE_LIMIT=3)
def test_successful_login_resets_the_count(client, college_a, make_user):
    make_user(college_a, "teacher")
    for _ in range(2):
        login(client, "teacher", password="wrong-password")
    assert login(client, "teacher").url == "/"
    client.logout()
    for _ in range(2):
        login(client, "teacher", password="wrong-password")
    assert login(client, "teacher").url == "/"


@override_settings(LOGIN_FAILURE_LIMIT=3, LOGIN_LOCKOUT_MINUTES=0)
def test_pause_ends_after_the_window(client, college_a, make_user):
    make_user(college_a, "teacher")
    for _ in range(3):
        login(client, "teacher", password="wrong-password")
    assert login(client, "teacher").url == "/"


@override_settings(LOGIN_FAILURE_LIMIT=3)
def test_admin_login_pauses_too(client, college_a, make_user):
    make_user(college_a, "teacher", roles=[Role.PRINCIPAL])
    for _ in range(3):
        client.post(
            "/admin/login/", {"username": "teacher", "password": "nope-nope-1"}, HTTP_HOST=ALPHA
        )
    response = client.post(
        "/admin/login/",
        {"username": "teacher", "password": PASSWORD, "next": "/admin/"},
        HTTP_HOST=ALPHA,
    )
    assert response.status_code == 200
    assert b"Too many wrong passwords" in response.content
