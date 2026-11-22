"""Forgot password: emailed reset links, scoped to one college (D24)."""

import re

import pytest
from django.core import mail
from django.test import override_settings

from apps.accounts.links import reset_tokens
from apps.accounts.roles import Role
from apps.audit.models import AuditEvent

pytestmark = pytest.mark.django_db

ALPHA = "alpha.localhost"
BETA = "beta.localhost"
NEW_PASSWORD = "a-fresh-long-pass-7"
LINK = re.compile(r"http://alpha\.localhost(/password/reset/[^/\s]+/[^/\s]+/)")


def ask(client, username, host=ALPHA):
    return client.post("/password/forgot/", {"username": username}, HTTP_HOST=host)


def emailed_path():
    match = LINK.search(mail.outbox[-1].body)
    assert match, mail.outbox[-1].body
    return match.group(1)


def choose(client, path, password=NEW_PASSWORD, host=ALPHA):
    """Open the link (Django moves the token into the session), then post the new password."""
    opened = client.get(path, HTTP_HOST=host)
    if opened.status_code != 302:
        return opened
    return client.post(
        opened.url, {"new_password1": password, "new_password2": password}, HTTP_HOST=host
    )


def requests(college):
    return AuditEvent.all_colleges.filter(college=college, action=AuditEvent.Action.RESET_REQUESTED)


@pytest.fixture
def teacher(college_a, make_user):
    return make_user(
        college_a, "teacher@alpha.test", email="teacher@alpha.test", roles=[Role.FACULTY]
    )


def test_login_page_links_to_forgot_password(client, college_a):
    assert b"/password/forgot/" in client.get("/login/", HTTP_HOST=ALPHA).content


def test_reset_link_sets_a_new_password(client, teacher, college_a):
    response = ask(client, "teacher@alpha.test")
    assert response.url == "/password/forgot/sent/"
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["teacher@alpha.test"]
    assert "Alpha College of Engineering" in message.subject
    done = choose(client, emailed_path())
    assert done.url == "/login/"
    teacher.refresh_from_db()
    assert teacher.check_password(NEW_PASSWORD)
    assert (
        client.post(
            "/login/", {"username": "teacher@alpha.test", "password": NEW_PASSWORD}, HTTP_HOST=ALPHA
        ).url
        == "/"
    )
    assert requests(college_a).get().extra == {"sent": True}
    assert AuditEvent.all_colleges.filter(
        college=college_a, action=AuditEvent.Action.PASSWORD_SET, object_id=str(teacher.pk)
    ).exists()


def test_link_works_only_once(client, teacher):
    ask(client, "teacher@alpha.test")
    path = emailed_path()
    choose(client, path)
    again = choose(client, path, password="another-long-pass-8")
    assert b"no longer works" in again.content
    teacher.refresh_from_db()
    assert teacher.check_password(NEW_PASSWORD)


def test_link_expires(client, teacher):
    ask(client, "teacher@alpha.test")
    path = emailed_path()
    with override_settings(PASSWORD_RESET_TIMEOUT=-1):
        assert b"no longer works" in choose(client, path).content


def test_link_does_not_work_on_another_college(client, teacher, college_b):
    ask(client, "teacher@alpha.test")
    assert b"no longer works" in choose(client, emailed_path(), host=BETA).content


def test_tampered_link_is_refused(client, teacher):
    ask(client, "teacher@alpha.test")
    path = emailed_path()
    assert b"no longer works" in choose(client, path[:-3] + "xx/").content
    assert b"no longer works" in choose(client, "/password/reset/!!/abc-def/").content


def test_student_can_reset_by_roll_number_even_without_a_password(client, college_a, make_user):
    student = make_user(
        college_a, "24CS001", password=None, email="kid@example.test", is_staff=False
    )
    ask(client, "24CS001")
    choose(client, emailed_path())
    student.refresh_from_db()
    assert student.check_password(NEW_PASSWORD)


def test_same_reply_for_unknown_account_and_no_email_sent(client, college_a, teacher):
    known = ask(client, "teacher@alpha.test")
    unknown = ask(client, "nobody@alpha.test")
    assert known.url == unknown.url == "/password/forgot/sent/"
    assert len(mail.outbox) == 1
    assert requests(college_a).filter(extra__username="nobody@alpha.test").exists()


def test_account_without_email_gets_nothing(client, college_a, make_user):
    make_user(college_a, "24CS009", password=None, is_staff=False)
    assert ask(client, "24CS009").url == "/password/forgot/sent/"
    assert mail.outbox == []
    assert requests(college_a).get().extra == {"sent": False, "reason": "no_email"}


def test_inactive_account_gets_nothing(client, college_a, make_user):
    make_user(college_a, "gone", email="gone@alpha.test", is_active=False)
    ask(client, "gone")
    assert mail.outbox == []


def test_email_of_another_college_is_not_found(client, teacher, college_b):
    ask(client, "teacher@alpha.test", host=BETA)
    assert mail.outbox == []


def test_lookup_by_email_needs_a_single_match(client, college_a, make_user):
    make_user(college_a, "24CS010", email="family@example.test", is_staff=False)
    make_user(college_a, "24CS011", email="family@example.test", is_staff=False)
    ask(client, "family@example.test")
    assert mail.outbox == []
    ask(client, "24CS011")
    assert mail.outbox[0].to == ["family@example.test"]


@override_settings(PASSWORD_RESET_EMAILS_PER_HOUR=2)
def test_reset_emails_are_limited_per_hour(client, college_a, teacher):
    for _ in range(4):
        ask(client, "teacher@alpha.test")
    assert len(mail.outbox) == 2
    assert requests(college_a).filter(extra__reason="too_many").count() == 2


def test_signing_in_invalidates_an_unused_link(client, teacher):
    ask(client, "teacher@alpha.test")
    path = emailed_path()
    client.post(
        "/login/",
        {"username": "teacher@alpha.test", "password": "correct-horse-1"},
        HTTP_HOST=ALPHA,
    )
    client.logout()
    assert b"no longer works" in choose(client, path).content


def test_token_is_tied_to_the_college(teacher, college_b):
    token = reset_tokens.make_token(teacher)
    assert reset_tokens.check_token(teacher, token)
    teacher.college_id = college_b.pk
    assert not reset_tokens.check_token(teacher, token)
    assert not reset_tokens.check_token(teacher, "")
    assert not reset_tokens.check_token(teacher, "nodash")
    assert not reset_tokens.check_token(teacher, "zz!-abc")
