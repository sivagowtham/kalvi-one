"""Login, logout and password change pages, served on each college's own host (D6, D23)."""

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.generic import FormView, TemplateView

from apps.audit import recorder
from apps.audit.models import AuditEvent

from . import links
from .forms import ForgotPasswordForm, LoginForm
from .models import User
from .permissions import public, require_login


class CollegeContextMixin:
    """Every account page shows which college the person is signing in to."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["college"] = getattr(self.request, "college", None)
        return context


class LoginView(CollegeContextMixin, auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


login_view = public(LoginView.as_view())


class LogoutView(auth_views.LogoutView):
    """POST only (Django 5). Clears the session and returns to the login page."""

    next_page = reverse_lazy("accounts:login")

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        messages.info(request, "You have signed out.")
        return response


logout_view = public(LogoutView.as_view())


class PasswordChangeView(CollegeContextMixin, auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("home")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Your password has been changed.")
        return response


password_change_view = require_login(PasswordChangeView.as_view())


class ForgotPasswordView(CollegeContextMixin, FormView):
    """Ask for a reset link. The reply is the same whether or not the account exists (D24)."""

    template_name = "accounts/forgot_password.html"
    form_class = ForgotPasswordForm

    def form_valid(self, form):
        user = form.get_user(self.request.college)
        if user is None:
            recorder.record(
                AuditEvent.Action.RESET_REQUESTED,
                extra={"username": form.cleaned_data["username"][:150], "sent": False},
            )
        else:
            links.send_reset_email(self.request, user)
        return redirect("accounts:forgot_password_sent")


forgot_password_view = public(ForgotPasswordView.as_view())


class ForgotPasswordSentView(CollegeContextMixin, TemplateView):
    template_name = "accounts/forgot_password_sent.html"


forgot_password_sent_view = public(ForgotPasswordSentView.as_view())


class SetPasswordFromLinkView(CollegeContextMixin, auth_views.PasswordResetConfirmView):
    """Open an emailed link and choose a password. Only this college's users (D6, D24).

    Django's view moves the token out of the address bar into the session before showing
    the form, so it does not leak through the Referer header.
    """

    template_name = "accounts/set_password.html"
    token_generator = links.reset_tokens
    success_message = "Your new password is set. Please sign in."

    def get_user(self, uidb64):
        try:
            pk = int(force_str(urlsafe_base64_decode(uidb64)))
        except (TypeError, ValueError, OverflowError):
            return None
        return User.objects.filter(pk=pk, college=self.request.college, is_active=True).first()

    def form_valid(self, form):
        form.save()  # the User update event records that the password changed, masked
        recorder.record(AuditEvent.Action.PASSWORD_SET, instance=self.user, actor=self.user)
        del self.request.session[auth_views.INTERNAL_RESET_SESSION_TOKEN]
        messages.success(self.request, self.success_message)
        return redirect("accounts:login")


reset_confirm_view = public(SetPasswordFromLinkView.as_view())


class AcceptInviteView(SetPasswordFromLinkView):
    """The link in an invite email: choose a first password (D25)."""

    template_name = "accounts/accept_invite.html"
    token_generator = links.invite_tokens
    success_message = "Welcome! Your password is set. Please sign in."


invite_accept_view = public(AcceptInviteView.as_view())


@require_login
def home(request):
    """Landing page after login. Modules add their links here as they get their own pages."""
    user = request.user
    return render(
        request,
        "accounts/home.html",
        {
            "college": request.college,
            "roles": sorted(role.label for role in user.roles()),
            "can_open_admin": user.is_staff,
        },
    )
