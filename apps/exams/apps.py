from django.apps import AppConfig


class ExamsConfig(AppConfig):
    name = "apps.exams"
    label = "exams"
    verbose_name = "Exams and marks"

    def ready(self) -> None:
        from . import grants  # noqa: F401
