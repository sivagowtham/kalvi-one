"""Audit records made during real requests: actor, request data, logins, denials."""

import pytest

from apps.accounts.roles import Role
from apps.audit.models import AuditEvent

pytestmark = pytest.mark.django_db
Action = AuditEvent.Action
ALPHA = "alpha.localhost"


def test_admin_change_records_actor_and_request_details(client, college_a, make_user):
    principal = make_user(college_a, "principal", roles=[Role.PRINCIPAL])
    teacher = make_user(college_a, "teacher")
    client.force_login(principal)
    response = client.post(
        "/admin/accounts/roleassignment/add/",
        {"user": teacher.pk, "role": Role.FACULTY},
        HTTP_HOST=ALPHA,
        HTTP_USER_AGENT="pytest-browser",
        HTTP_X_REQUEST_ID="req-123",
    )
    assert response.status_code == 302
    assert response["X-Request-ID"] == "req-123"
    event = AuditEvent.all_colleges.filter(action=Action.CREATE, object_repr__contains="teacher")
    event = event.latest("id")
    assert event.actor == principal
    assert event.actor_label == "principal"
    assert event.request_id == "req-123"
    assert event.user_agent == "pytest-browser"
    assert event.ip_address == "127.0.0.1"
    assert event.college == college_a


def test_successful_and_failed_logins_are_recorded(client, college_a, make_user):
    make_user(college_a, "teacher", password="right-password-1")
    client.post(
        "/admin/login/", {"username": "teacher", "password": "nope-nope-1"}, HTTP_HOST=ALPHA
    )
    client.post(
        "/admin/login/", {"username": "teacher", "password": "right-password-1"}, HTTP_HOST=ALPHA
    )
    failed = AuditEvent.all_colleges.get(action=Action.LOGIN_FAILED)
    assert failed.college == college_a
    assert failed.extra == {"username": "teacher"}
    assert "nope" not in str(failed.extra)
    login = AuditEvent.all_colleges.get(action=Action.LOGIN)
    assert login.actor_label == "teacher"
    client.post("/admin/logout/", HTTP_HOST=ALPHA)
    assert AuditEvent.all_colleges.filter(action=Action.LOGOUT).count() == 1


def test_permission_denied_is_recorded_and_survives_the_request(client, college_a, make_user):
    client.force_login(make_user(college_a, "clerk", roles=[Role.OFFICE]))
    response = client.get("/testapp/widgets/", HTTP_HOST=ALPHA)
    assert response.status_code == 403
    denied = AuditEvent.all_colleges.get(action=Action.PERMISSION_DENIED)
    assert denied.actor_label == "clerk"
    assert denied.extra == {"permission": "testapp.view_widget", "path": "/testapp/widgets/"}


def test_audit_admin_is_read_only_and_principal_only(client, college_a, make_user):
    client.force_login(make_user(college_a, "principal", roles=[Role.PRINCIPAL]))
    page = client.get("/admin/audit/auditevent/", HTTP_HOST=ALPHA)
    assert page.status_code == 200
    event = AuditEvent.all_colleges.filter(college=college_a).first()
    detail = client.get(f"/admin/audit/auditevent/{event.pk}/change/", HTTP_HOST=ALPHA)
    assert detail.status_code == 200
    assert b'name="_save"' not in detail.content
    assert client.get("/admin/audit/auditevent/add/", HTTP_HOST=ALPHA).status_code == 403
    client.force_login(make_user(college_a, "clerk", roles=[Role.OFFICE]))
    assert client.get("/admin/audit/auditevent/", HTTP_HOST=ALPHA).status_code == 403
