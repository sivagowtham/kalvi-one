"""Login, logout and password change pages, served on each college's own host (D6, D23)."""

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.shortcuts import render
from django.urls import reverse_lazy

from .forms import LoginForm
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
