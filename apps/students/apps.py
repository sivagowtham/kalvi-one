from django.apps import AppConfig


class StudentsConfig(AppConfig):
    name = "apps.students"
    label = "students"
    verbose_name = "Students"

    def ready(self) -> None:
        from . import grants  # noqa: F401
