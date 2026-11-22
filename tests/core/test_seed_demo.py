"""The seed_demo command (fake data only, D10)."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from apps.academics.models import AcademicYear, Course, Department, Programme, Semester
from apps.accounts.models import User
from apps.accounts.roles import Role
from apps.audit.models import AuditEvent
from apps.students.models import Batch, Consent, Guardian, Section, Student
from apps.tenancy.context import college_context
from apps.tenancy.models import College

pytestmark = pytest.mark.django_db


def seed(*args):
    out = StringIO()
    call_command("seed_demo", *args, stdout=out)
    return out.getvalue()


def counts():
    return {
        model.__name__: model.all_colleges.count()
        for model in (
            Department,
            Programme,
            Course,
            AcademicYear,
            Semester,
            Batch,
            Section,
            Student,
            Guardian,
            Consent,
        )
    } | {"users": User.objects.count(), "colleges": College.objects.count()}


def test_creates_one_user_per_role():
    output = seed()
    demo = College.objects.get(slug="demo")
    users = User.objects.filter(college=demo)
    held = {role for user in users for role in user.roles()}
    assert held == set(Role)
    assert "http://demo.localhost:8000/admin/" in output
    hod = users.get(username="hod@demo.example")
    assert hod.roles() == {Role.HOD, Role.FACULTY}
    assert not users.get(username="26DCE001").is_staff
    assert users.get(username="principal@demo.example").is_staff


def test_is_idempotent():
    seed("--with-second-college")
    first = counts()
    seed("--with-second-college")
    assert counts() == first
    assert first["colleges"] == 2


def test_creates_academic_structure():
    seed()
    with college_context(College.objects.get(slug="demo")):
        assert Department.objects.count() == 3
        assert Programme.objects.count() == 2
        assert Course.objects.count() == 6
        assert AcademicYear.objects.get(is_current=True).label == "2026-27"
        assert Semester.objects.get(is_current=True).term == "odd"
        assert sorted(Batch.objects.values_list("label", flat=True)) == ["2026-2030"] * 2
        assert Section.objects.count() == 4
        assert Student.objects.count() == 12
        assert Guardian.objects.count() == 24
        assert Consent.objects.count() == 12
        first = Student.objects.get(roll_number="26DCE001")
        assert first.user.username == "26DCE001"
        assert first.has_secret("aadhaar")


def test_demo_users_can_log_in_on_their_college_only(client):
    seed("--with-second-college", "--password", "another-demo-pw-1")
    login = {"username": "principal@demo.example", "password": "another-demo-pw-1"}
    ok = client.post("/admin/login/", {**login, "next": "/admin/"}, HTTP_HOST="demo.localhost")
    assert ok.status_code == 302
    client.logout()
    refused = client.post("/admin/login/", login, HTTP_HOST="sample.localhost")
    assert refused.status_code == 200


def test_colleges_stay_isolated():
    seed("--with-second-college")
    with college_context(College.objects.get(slug="sample")):
        assert set(Department.objects.values_list("code", flat=True)) == {"ENG", "COM"}


def test_changes_are_audited_as_seed_demo():
    seed()
    assert AuditEvent.all_colleges.filter(actor_label="seed_demo").exists()
    assert (
        not AuditEvent.all_colleges.exclude(actor_label="seed_demo")
        .filter(action="create")
        .exists()
    )


@override_settings(ALLOW_DEMO_SEED=False)
def test_refuses_when_not_allowed():
    with pytest.raises(CommandError, match="disabled"):
        seed()
    assert College.objects.count() == 0
