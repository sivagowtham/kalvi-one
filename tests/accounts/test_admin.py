"""User administration stays inside one college."""

import pytest

from apps.accounts.models import RoleAssignment, User
from apps.accounts.roles import Role

pytestmark = pytest.mark.django_db

ALPHA = "alpha.localhost"


@pytest.fixture
def principal(client, college_a, make_user):
    user = make_user(college_a, "principal", roles=[Role.PRINCIPAL])
    client.force_login(user)
    return user


def test_user_list_shows_only_own_college(client, principal, college_b, make_user):
    make_user(college_b, "outsider")
    User.objects.create_superuser("root", "pw-root-123")
    page = client.get("/admin/accounts/user/", HTTP_HOST=ALPHA)
    assert page.status_code == 200
    assert b"principal" in page.content
    assert b"outsider" not in page.content
    assert b"root" not in page.content


def test_cannot_open_another_colleges_user(client, principal, college_b, make_user):
    outsider = make_user(college_b, "outsider")
    page = client.get(f"/admin/accounts/user/{outsider.pk}/change/", HTTP_HOST=ALPHA)
    assert page.status_code == 302  # admin redirects when the object is not in the queryset


def test_added_user_joins_the_current_college(client, principal, college_a):
    response = client.post(
        "/admin/accounts/user/add/",
        {
            "username": "newteacher",
            "full_name": "New Teacher",
            "email": "",
            "phone": "",
            "is_staff": "on",
            "password1": "a-long-password-1",
            "password2": "a-long-password-1",
        },
        HTTP_HOST=ALPHA,
    )
    assert response.status_code == 302, response.content
    created = User.objects.get(username="newteacher")
    assert created.college == college_a
    assert created.check_password("a-long-password-1")


def test_mismatched_passwords_are_rejected(client, principal):
    response = client.post(
        "/admin/accounts/user/add/",
        {"username": "x", "password1": "one-password-1", "password2": "two-password-2"},
        HTTP_HOST=ALPHA,
    )
    assert response.status_code == 200
    assert b"do not match" in response.content
    assert not User.objects.filter(username="x").exists()


def test_change_page_and_password_page_load(client, principal, make_user, college_a):
    teacher = make_user(college_a, "teacher", roles=[Role.FACULTY])
    assert (
        client.get(f"/admin/accounts/user/{teacher.pk}/change/", HTTP_HOST=ALPHA).status_code == 200
    )
    password_page = client.get(f"/admin/accounts/user/{teacher.pk}/password/", HTTP_HOST=ALPHA)
    assert password_page.status_code == 200


def test_office_can_manage_users_and_see_but_not_grant_roles(client, college_a, make_user):
    client.force_login(make_user(college_a, "clerk", roles=[Role.OFFICE]))
    teacher = make_user(college_a, "teacher", roles=[Role.FACULTY])
    assert client.get("/admin/accounts/user/", HTTP_HOST=ALPHA).status_code == 200
    assert client.get("/admin/accounts/roleassignment/", HTTP_HOST=ALPHA).status_code == 200
    assert client.get("/admin/accounts/roleassignment/add/", HTTP_HOST=ALPHA).status_code == 403
    page = client.get(f"/admin/accounts/user/{teacher.pk}/change/", HTTP_HOST=ALPHA)
    assert page.status_code == 200


def test_faculty_cannot_open_user_admin(client, college_a, make_user):
    client.force_login(make_user(college_a, "teacher", roles=[Role.FACULTY]))
    assert client.get("/admin/accounts/user/", HTTP_HOST=ALPHA).status_code == 403


def test_principal_can_grant_roles_to_own_college_only(
    client, principal, college_a, college_b, make_user
):
    teacher = make_user(college_a, "teacher")
    outsider = make_user(college_b, "outsider")
    page = client.get("/admin/accounts/roleassignment/add/", HTTP_HOST=ALPHA)
    assert page.status_code == 200
    response = client.post(
        "/admin/accounts/roleassignment/add/",
        {"user": outsider.pk, "role": Role.FACULTY},
        HTTP_HOST=ALPHA,
    )
    assert response.status_code == 200  # form error: outsider is not a choice
    assert not RoleAssignment.all_colleges.filter(user=outsider).exists()
    response = client.post(
        "/admin/accounts/roleassignment/add/",
        {"user": teacher.pk, "role": Role.FACULTY},
        HTTP_HOST=ALPHA,
    )
    assert response.status_code == 302
    assert teacher.roles() == {Role.FACULTY}
