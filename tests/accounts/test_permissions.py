"""Default-deny role permissions (D7)."""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ImproperlyConfigured

from apps.accounts import permissions
from apps.accounts.models import User
from apps.accounts.permissions import UnknownPermission, has_perm, register, require_perm
from apps.accounts.roles import Role
from apps.tenancy.context import college_context

pytestmark = pytest.mark.django_db


def test_role_grants_exactly_what_is_registered(college_a, make_user):
    faculty = make_user(college_a, "teacher", roles=[Role.FACULTY])
    office = make_user(college_a, "clerk", roles=[Role.OFFICE])
    with college_context(college_a):
        assert has_perm(faculty, "testapp.view_widget")
        assert not has_perm(faculty, "testapp.change_widget")
        assert not has_perm(office, "testapp.view_widget")


def test_several_roles_combine(college_a, make_user):
    user = make_user(college_a, "both", roles=[Role.OFFICE, Role.FACULTY])
    with college_context(college_a):
        assert has_perm(user, "testapp.view_widget")
        assert has_perm(user, "accounts.add_user")


def test_user_without_roles_gets_nothing(college_a, make_user):
    user = make_user(college_a, "nobody")
    with college_context(college_a):
        assert not any(has_perm(user, code) for code in permissions.registered())


def test_unknown_code_raises_in_code_but_is_denied_for_django(college_a, make_user):
    principal = make_user(college_a, "boss", roles=[Role.PRINCIPAL])
    with college_context(college_a):
        with pytest.raises(UnknownPermission):
            has_perm(principal, "nothing.like_this")
        assert principal.has_perm("nothing.like_this") is False


def test_denied_outside_own_college(college_a, college_b, make_user):
    faculty = make_user(college_a, "teacher", roles=[Role.FACULTY])
    assert not has_perm(faculty, "testapp.view_widget")  # no college at all
    with college_context(college_b):
        assert not has_perm(faculty, "testapp.view_widget")


def test_anonymous_and_inactive_are_denied(college_a, make_user):
    inactive = make_user(college_a, "gone", roles=[Role.PRINCIPAL], is_active=False)
    with college_context(college_a):
        assert not has_perm(AnonymousUser(), "testapp.view_widget")
        assert not has_perm(inactive, "testapp.view_widget")
        assert not has_perm(None, "testapp.view_widget")


def test_platform_superuser_only_on_platform(college_a):
    root = User.objects.create_superuser("root", "pw-root-123")
    plain = User.objects.create_user("support", "pw-support-1")
    assert has_perm(root, "testapp.view_widget")
    assert not has_perm(plain, "testapp.view_widget")
    with college_context(college_a):
        assert not has_perm(root, "testapp.view_widget")


def test_django_perm_api_uses_registry(college_a, make_user):
    principal = make_user(college_a, "boss", roles=[Role.PRINCIPAL])
    with college_context(college_a):
        assert principal.has_perms(["testapp.view_widget", "testapp.change_widget"])
        assert principal.has_module_perms("testapp")
        assert not principal.has_module_perms("nonexistent")


def test_registry_rejects_duplicates_and_unknown_decorator_codes():
    with pytest.raises(ImproperlyConfigured):
        register("testapp.view_widget", [Role.FACULTY], "again")
    with pytest.raises(ImproperlyConfigured):
        require_perm("not.registered")


class TestProtectedView:
    url = "/testapp/widgets/"

    def test_anonymous_is_sent_to_login(self, client, college_a):
        response = client.get(self.url, HTTP_HOST="alpha.localhost")
        assert response.status_code == 302
        assert "/admin/login/" in response.url

    def test_role_with_permission_gets_in(self, client, college_a, make_user):
        client.force_login(make_user(college_a, "teacher", roles=[Role.FACULTY]))
        response = client.get(self.url, HTTP_HOST="alpha.localhost")
        assert response.status_code == 200

    def test_role_without_permission_gets_403_and_signal(self, client, college_a, make_user):
        received = []

        def listener(sender, request, code, **kwargs):
            received.append(code)

        permissions.permission_denied.connect(listener)
        try:
            client.force_login(make_user(college_a, "clerk", roles=[Role.OFFICE]))
            response = client.get(self.url, HTTP_HOST="alpha.localhost")
        finally:
            permissions.permission_denied.disconnect(listener)
        assert response.status_code == 403
        assert received == ["testapp.view_widget"]

    def test_public_view_needs_no_login(self, client, college_a):
        assert client.get("/testapp/open/", HTTP_HOST="alpha.localhost").status_code == 200
