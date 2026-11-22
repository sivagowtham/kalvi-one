from django.apps import AppConfig


class AcademicsConfig(AppConfig):
    name = "apps.academics"
    label = "academics"
    verbose_name = "Academics"

    def ready(self) -> None:
        from . import grants  # noqa: F401
