from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _

from apps.audit import recorder
from apps.audit.models import AuditEvent

from . import throttle


class ThrottledLoginMixin:
    """Refuse to check the password once a username is paused (D23)."""

    locked_message = _(
        "Too many wrong passwords. Please wait %(minutes)s minutes and try again, "
        "or use “Forgot password?”."
    )

    def clean(self):
        username = self.cleaned_data.get("username")
        if username and self.request is not None and throttle.is_locked(self.request, username):
            recorder.record(
                AuditEvent.Action.LOGIN_FAILED,
                extra={"username": username, "reason": throttle.LOCKED_REASON},
            )
            from django.conf import settings

            raise forms.ValidationError(
                self.locked_message,
                code="locked",
                params={"minutes": settings.LOGIN_LOCKOUT_MINUTES},
            )
        return super().clean()


class LoginForm(ThrottledLoginMixin, AuthenticationForm):
    """The college login page. Staff use their email, students their roll number (D6)."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": _("That username and password do not match. Please try again."),
    }

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields["username"].label = _("Email or roll number")
        self.fields["username"].widget.attrs.update(autocomplete="username", autocapitalize="none")
        self.fields["password"].widget.attrs.update(autocomplete="current-password")


class AdminLoginForm(ThrottledLoginMixin, AdminAuthenticationForm):
    """Django admin's own login form, with the same pause after wrong passwords."""
