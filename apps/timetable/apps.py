from django.apps import AppConfig


class TimetableConfig(AppConfig):
    name = "apps.timetable"
    label = "timetable"
    verbose_name = "Timetable"

    def ready(self) -> None:
        from . import grants  # noqa: F401
