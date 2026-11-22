from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Users and roles"

    def ready(self) -> None:
        from django.contrib import admin

        from . import grants  # noqa: F401  (registers this app's permissions)
        from .forms import AdminLoginForm

        # The admin login pauses after repeated wrong passwords, like the main login (D23).
        admin.site.login_form = AdminLoginForm
