"""Login is tied to the college of the request host (D6)."""

import pytest
from django.db import IntegrityError

from apps.accounts.models import RoleAssignment, User
from apps.accounts.roles import Role
from apps.tenancy.context import CrossCollegeError

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-1"


def admin_login(client, host, username, password=PASSWORD):
    return client.post(
        "/admin/login/",
        {"username": username, "password": password, "next": "/admin/"},
        HTTP_HOST=host,
    )


def logged_in(response) -> bool:
    return response.status_code == 302 and response.url == "/admin/"


def test_user_logs_in_on_own_college_host(client, college_a, make_user):
    make_user(college_a, "teacher", roles=[Role.FACULTY])
    assert logged_in(admin_login(client, "alpha.localhost", "teacher"))


def test_user_cannot_log_in_on_another_college_host(client, college_a, college_b, make_user):
    make_user(college_a, "teacher", roles=[Role.FACULTY])
    assert not logged_in(admin_login(client, "beta.localhost", "teacher"))


def test_wrong_password_is_refused(client, college_a, make_user):
    make_user(college_a, "teacher")
    assert not logged_in(admin_login(client, "alpha.localhost", "teacher", "wrong-password"))


def test_inactive_user_is_refused(client, college_a, make_user):
    make_user(college_a, "teacher", is_active=False)
    assert not logged_in(admin_login(client, "alpha.localhost", "teacher"))


def test_same_username_in_two_colleges(client, college_a, college_b, make_user):
    make_user(college_a, "21cs001", password="alpha-pass-123")
    make_user(college_b, "21cs001", password="beta-pass-123")
    assert logged_in(admin_login(client, "alpha.localhost", "21cs001", "alpha-pass-123"))
    client.logout()
    assert not logged_in(admin_login(client, "beta.localhost", "21cs001", "alpha-pass-123"))
    assert logged_in(admin_login(client, "beta.localhost", "21cs001", "beta-pass-123"))


def test_platform_superuser_logs_in_only_on_platform_host(client, college_a):
    User.objects.create_superuser("root", PASSWORD)
    assert not logged_in(admin_login(client, "alpha.localhost", "root"))
    assert logged_in(admin_login(client, "localhost", "root"))


def test_session_from_one_college_is_ignored_on_another(client, college_a, college_b, make_user):
    client.force_login(make_user(college_a, "principal", roles=[Role.PRINCIPAL]))
    assert client.get("/admin/", HTTP_HOST="alpha.localhost").status_code == 200
    response = client.get("/admin/", HTTP_HOST="beta.localhost")
    assert response.status_code == 302
    assert "/admin/login/" in response.url


def test_duplicate_username_in_same_college_is_refused(college_a, make_user):
    make_user(college_a, "teacher")
    with pytest.raises(IntegrityError):
        make_user(college_a, "teacher")


def test_superuser_must_be_platform_staff(college_a):
    with pytest.raises(IntegrityError):
        User.objects.create_user("bad", PASSWORD, college=college_a, is_superuser=True)


def test_username_is_required():
    with pytest.raises(ValueError, match="username"):
        User.objects.create_user("", PASSWORD)


def test_platform_staff_cannot_hold_college_roles(db):
    root = User.objects.create_superuser("root", PASSWORD)
    with pytest.raises(CrossCollegeError):
        RoleAssignment.all_colleges.create(user=root, role=Role.PRINCIPAL)


def test_role_must_be_in_users_own_college(college_a, college_b, make_user):
    user = make_user(college_a, "teacher")
    with pytest.raises(CrossCollegeError):
        RoleAssignment.all_colleges.create(user=user, role=Role.FACULTY, college=college_b)


def test_user_display_helpers(college_a, make_user):
    user = make_user(college_a, "teacher", roles=[Role.FACULTY, Role.OFFICE], full_name="Asha Devi")
    assert str(user) == "Asha Devi"
    assert user.get_full_name() == "Asha Devi"
    assert user.get_short_name() == "Asha"
    assert user.roles() == {Role.FACULTY, Role.OFFICE}
    assert not user.is_platform_staff
    assert str(user.role_assignments.model.all_colleges.first()).startswith("Asha Devi as")
    bare = make_user(college_a, "nobody")
    assert str(bare) == "nobody"
    assert bare.get_short_name() == "nobody"
    root = User.objects.create_superuser("root", PASSWORD)
    assert root.roles() == frozenset()
