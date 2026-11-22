from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Users and roles"

    def ready(self) -> None:
        from . import grants  # noqa: F401  (registers this app's permissions)
