from django.apps import AppConfig


class AdmissionsConfig(AppConfig):
    name = "apps.admissions"
    label = "admissions"
    verbose_name = "Admissions"

    def ready(self) -> None:
        from . import grants  # noqa: F401
