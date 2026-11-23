from django.apps import AppConfig


class FeesConfig(AppConfig):
    name = "apps.fees"
    label = "fees"
    verbose_name = "Fees"

    def ready(self) -> None:
        from . import grants  # noqa: F401
