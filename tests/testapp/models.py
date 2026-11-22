from django.db import models

from apps.audit.mixins import Audited
from apps.tenancy.models import TenantModel


class Widget(TenantModel):
    name = models.CharField(max_length=50)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["college", "name"], name="testapp_unique_widget_name")
        ]

    def __str__(self) -> str:
        return self.name


class Gadget(Audited, TenantModel):
    audit_mask = ("secret",)

    widget = models.ForeignKey(Widget, on_delete=models.CASCADE, related_name="gadgets")
    label = models.CharField(max_length=50)
    secret = models.CharField(max_length=50, blank=True)

    def __str__(self) -> str:
        return self.label
