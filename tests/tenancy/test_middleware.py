"""Tenant resolution from the request host (D2, D12)."""

import pytest
from django.test import override_settings

from apps.accounts.roles import Role
from apps.tenancy.context import college_context
from tests.testapp.models import Widget

pytestmark = pytest.mark.django_db


def test_subdomain_resolves_college(client, college_a):
    response = client.get("/health/", HTTP_HOST="alpha.localhost")
    assert response.status_code == 200
    assert response.wsgi_request.college == college_a


def test_port_in_host_is_ignored(client, college_a):
    response = client.get("/health/", HTTP_HOST="alpha.localhost:8000")
    assert response.wsgi_request.college == college_a


def test_platform_host_has_no_college(client, college_a):
    response = client.get("/health/", HTTP_HOST="localhost")
    assert response.status_code == 200
    assert response.wsgi_request.college is None


def test_unknown_subdomain_is_404(client, college_a):
    assert client.get("/health/", HTTP_HOST="gamma.localhost").status_code == 404


def test_inactive_college_is_404(client, college_a):
    college_a.is_active = False
    college_a.save()
    assert client.get("/health/", HTTP_HOST="alpha.localhost").status_code == 404


def test_nested_subdomain_is_404(client, college_a):
    assert client.get("/health/", HTTP_HOST="x.alpha.localhost").status_code == 404


@override_settings(ALLOWED_HOSTS=["*"])
def test_host_outside_base_domains_is_404(client, college_a):
    assert client.get("/health/", HTTP_HOST="alpha.example.com").status_code == 404


@override_settings(TENANT_DEDICATED_COLLEGE_SLUG="beta")
def test_dedicated_deployment_serves_one_college_on_any_host(client, college_a, college_b):
    response = client.get("/health/", HTTP_HOST="localhost")
    assert response.wsgi_request.college == college_b


def test_context_is_cleared_after_request(client, college_a):
    from apps.tenancy.context import get_current_college

    client.get("/health/", HTTP_HOST="alpha.localhost")
    assert get_current_college() is None


def test_admin_lists_only_current_college_rows(client, college_a, college_b, make_user):
    with college_context(college_a):
        Widget.objects.create(name="alpha-widget")
    with college_context(college_b):
        Widget.objects.create(name="beta-widget")
    client.force_login(make_user(college_a, "principal", roles=[Role.PRINCIPAL]))
    alpha_page = client.get("/admin/testapp/widget/", HTTP_HOST="alpha.localhost")
    assert alpha_page.status_code == 200
    assert b"alpha-widget" in alpha_page.content
    assert b"beta-widget" not in alpha_page.content

    client.force_login(make_user(college_b, "principal", roles=[Role.PRINCIPAL]))
    beta_page = client.get("/admin/testapp/widget/", HTTP_HOST="beta.localhost")
    assert b"beta-widget" in beta_page.content
    assert b"alpha-widget" not in beta_page.content


def test_platform_host_hides_college_models_in_admin(client, college_a):
    from apps.accounts.models import User

    client.force_login(User.objects.create_superuser("root", "pw-root-123"))
    response = client.get("/admin/testapp/widget/", HTTP_HOST="localhost")
    assert response.status_code == 403
