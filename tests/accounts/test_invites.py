"""Invite emails: a link to choose a first password, sent from admin or a command (D25)."""

import re

import pytest
from django.core import mail
from django.core.management import CommandError, call_command
from django.test import override_settings

from apps.accounts.links import invite_tokens
from apps.accounts.roles import Role
from apps.audit.models import AuditEvent

pytestmark = pytest.mark.django_db

ALPHA = "alpha.localhost"
BETA = "beta.localhost"
NEW_PASSWORD = "my-first-long-pass-3"
LINK = re.compile(r"http://alpha\.localhost(/welcome/[^/\s]+/[^/\s]+/)")


def emailed_path(message):
    match = LINK.search(message.body)
    assert match, message.body
    return match.group(1)


def accept(client, path, host=ALPHA):
    opened = client.get(path, HTTP_HOST=host)
    if opened.status_code != 302:
        return opened
    return client.post(
        opened.url, {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}, HTTP_HOST=host
    )


@pytest.fixture
def office(client, college_a, make_user):
    user = make_user(college_a, "office@alpha.test", roles=[Role.OFFICE])
    client.force_login(user)
    return user


@pytest.fixture
def newcomer(college_a, make_user):
    return make_user(
        college_a,
        "newteacher@alpha.test",
        password=None,
        email="newteacher@alpha.test",
        full_name="Meena Pillai",
        roles=[Role.FACULTY],
    )


def invite_in_admin(client, *users):
    return client.post(
        "/admin/accounts/user/",
        {"action": "send_invites", "_selected_action": [u.pk for u in users]},
        HTTP_HOST=ALPHA,
        follow=True,
    )


def test_office_sends_invite_from_admin_and_newcomer_sets_password(
    client, office, newcomer, college_a
):
    page = invite_in_admin(client, newcomer)
    assert b"Sent 1 invite" in page.content
    message = mail.outbox[0]
    assert message.to == ["newteacher@alpha.test"]
    assert "Alpha College of Engineering" in message.subject
    assert "newteacher@alpha.test" in message.body and "7 days" in message.body
    client.logout()
    done = accept(client, emailed_path(message))
    assert done.url == "/login/"
    newcomer.refresh_from_db()
    assert newcomer.check_password(NEW_PASSWORD)
    sent = AuditEvent.all_colleges.get(college=college_a, action=AuditEvent.Action.INVITE_SENT)
    assert sent.actor == office and sent.object_id == str(newcomer.pk)


def test_invite_link_works_once(client, office, newcomer):
    invite_in_admin(client, newcomer)
    client.logout()
    path = emailed_path(mail.outbox[0])
    accept(client, path)
    assert b"no longer works" in accept(client, path).content


def test_invite_link_is_not_a_reset_link(client, office, newcomer):
    invite_in_admin(client, newcomer)
    client.logout()
    path = emailed_path(mail.outbox[0]).replace("/welcome/", "/password/reset/")
    assert b"no longer works" in accept(client, path).content


def test_invite_link_expires_and_stays_in_its_college(client, office, newcomer, college_b):
    invite_in_admin(client, newcomer)
    client.logout()
    path = emailed_path(mail.outbox[0])
    assert b"no longer works" in accept(client, path, host=BETA).content
    with override_settings(INVITE_LINK_TIMEOUT=-1):
        assert b"no longer works" in accept(client, path).content


def test_admin_skips_accounts_that_cannot_be_invited(client, office, college_a, make_user):
    has_password = make_user(college_a, "old@alpha.test", email="old@alpha.test")
    no_email = make_user(college_a, "24CS001", password=None, is_staff=False)
    page = invite_in_admin(client, has_password, no_email)
    assert b"Skipped 2" in page.content
    assert mail.outbox == []


def test_only_principal_and_office_can_invite(client, college_a, make_user, newcomer):
    client.force_login(make_user(college_a, "hod", roles=[Role.FACULTY]))
    page = client.get("/admin/accounts/user/", HTTP_HOST=ALPHA)
    assert b"send_invites" not in page.content
    invite_in_admin(client, newcomer)
    assert mail.outbox == []


def test_command_counts_then_sends(college_a, office, newcomer, make_user, capsys):
    student = make_user(
        college_a, "24CS002", password=None, email="s2@example.test", roles=[Role.STUDENT]
    )
    call_command("send_invites", college="alpha", username="office@alpha.test")
    assert "2 account(s) would get an invite" in capsys.readouterr().out
    assert mail.outbox == []
    call_command(
        "send_invites", college="alpha", username="office@alpha.test", only="students", send=True
    )
    assert "Sent 1 invite" in capsys.readouterr().out
    assert [m.to for m in mail.outbox] == [[student.email]]
    assert emailed_path(mail.outbox[0]).startswith("/welcome/")
    event = AuditEvent.all_colleges.get(action=AuditEvent.Action.INVITE_SENT)
    assert event.actor == office


def test_command_refuses_bad_input(college_a, make_user):
    make_user(college_a, "teacher", roles=[Role.FACULTY])
    with pytest.raises(CommandError, match="No active college"):
        call_command("send_invites", college="nowhere", username="teacher")
    with pytest.raises(CommandError, match="not a user"):
        call_command("send_invites", college="alpha", username="ghost")
    with pytest.raises(CommandError, match="may not send"):
        call_command("send_invites", college="alpha", username="teacher")


def test_invite_token_is_separate_from_reset(newcomer):
    from apps.accounts.links import reset_tokens

    token = invite_tokens.make_token(newcomer)
    assert invite_tokens.check_token(newcomer, token)
    assert not reset_tokens.check_token(newcomer, token)
