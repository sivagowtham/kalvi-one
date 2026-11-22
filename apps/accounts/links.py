"""Emailed one-time links for setting a password (D24).

A link carries the user's ID and a signed token. The token is tied to the user's college,
current password hash, last login and email, so it stops working as soon as the password
is set, the person signs in, or their email changes. It also expires.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.encoding import force_bytes
from django.utils.http import base36_to_int, urlsafe_base64_encode

from apps.audit import recorder
from apps.audit.models import AuditEvent


class LinkTokenGenerator(PasswordResetTokenGenerator):
    """Django's reset token with its own salt and its own lifetime setting."""

    def __init__(self, key_salt: str, timeout_setting: str):
        self.key_salt = key_salt
        self.timeout_setting = timeout_setting
        super().__init__()

    def _make_hash_value(self, user, timestamp):
        return f"{super()._make_hash_value(user, timestamp)}{user.college_id}"

    def check_token(self, user, token):
        # Same checks as Django's, but the lifetime comes from ``timeout_setting``.
        if not (user and token):
            return False
        try:
            ts_b36, _ = token.split("-")
            ts = base36_to_int(ts_b36)
        except ValueError:
            return False
        for secret in [self.secret, *self.secret_fallbacks]:
            if constant_time_compare(self._make_token_with_timestamp(user, ts, secret), token):
                break
        else:
            return False
        return (self._num_seconds(self._now()) - ts) <= getattr(settings, self.timeout_setting)


reset_tokens = LinkTokenGenerator("kalvione.accounts.reset", "PASSWORD_RESET_TIMEOUT")


def reset_emails_last_hour(user) -> int:
    since = timezone.now() - timedelta(hours=1)
    return AuditEvent.all_colleges.filter(
        college_id=user.college_id,
        action=AuditEvent.Action.RESET_REQUESTED,
        object_id=str(user.pk),
        extra__sent=True,
        created_at__gte=since,
    ).count()


def link_for(request, user, tokens, url_name: str) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    path = reverse(url_name, kwargs={"uidb64": uid, "token": tokens.make_token(user)})
    # The host is the college's own address; TenantMiddleware has already checked it.
    return request.build_absolute_uri(path)


def send_link_email(request, user, *, template: str, link: str, valid_for: str) -> None:
    context = {
        "user": user,
        "college": getattr(request, "college", None),
        "link": link,
        "valid_for": valid_for,
    }
    subject = render_to_string(f"accounts/email/{template}_subject.txt", context)
    body = render_to_string(f"accounts/email/{template}_body.txt", context)
    send_mail(" ".join(subject.split()), body, None, [user.email])


def send_reset_email(request, user) -> bool:
    """Email ``user`` a reset link unless they have no email or have had too many. Audited."""
    sent = bool(user.email) and (
        reset_emails_last_hour(user) < settings.PASSWORD_RESET_EMAILS_PER_HOUR
    )
    if sent:
        minutes = settings.PASSWORD_RESET_TIMEOUT // 60
        send_link_email(
            request,
            user,
            template="reset",
            link=link_for(request, user, reset_tokens, "accounts:reset_confirm"),
            valid_for=f"{minutes} minutes" if minutes < 120 else f"{minutes // 60} hours",
        )
    reason = "" if sent else ("no_email" if not user.email else "too_many")
    recorder.record(
        AuditEvent.Action.RESET_REQUESTED,
        instance=user,
        extra={"sent": sent, **({"reason": reason} if reason else {})},
    )
    return sent
