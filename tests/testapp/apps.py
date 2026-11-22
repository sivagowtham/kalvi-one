from django.apps import AppConfig


class TestAppConfig(AppConfig):
    """Models used only by the test suite to exercise TenantModel."""

    name = "tests.testapp"
    label = "testapp"

    def ready(self) -> None:
        from . import grants  # noqa: F401
