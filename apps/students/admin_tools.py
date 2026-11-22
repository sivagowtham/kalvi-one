"""Admin building blocks for records with sensitive fields (D18, D19).

Shared by the student admin and the admission application admin.
"""

from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from apps.accounts.permissions import has_perm

from . import config, crypto
from .validators import normalise_aadhaar

LABELS = {
    "aadhaar": "Aadhaar number",
    "community_cert_no": "Community certificate number",
    "annual_income": "Annual family income",
}


def sees_sensitive(request) -> bool:
    return has_perm(request.user, "students.view_sensitive")


class PersonForm(forms.ModelForm):
    """Write-only inputs for encrypted fields, and config-driven community and quota lists."""

    secret_inputs = {"aadhaar": "aadhaar_number", "community_cert_no": "community_cert_no"}
    duplicate_message = "Another record has this Aadhaar."

    aadhaar_number = forms.CharField(
        required=False,
        label="Aadhaar number",
        help_text="Type a new number to set or replace it. Stored encrypted; blank keeps it.",
    )
    community_cert_no = forms.CharField(
        required=False,
        label="Community certificate number",
        help_text="Type to set or replace it. Stored encrypted; blank keeps it.",
    )

    def __init__(self, *args, college=None, **kwargs):
        super().__init__(*args, **kwargs)
        if college is not None:
            for name, key in [("community", "communities"), ("quota", "quotas")]:
                if name in self.fields:
                    self.fields[name] = forms.ChoiceField(
                        choices=[("", "---------"), *config.choices(college, key)],
                        required=False,
                        label=self.fields[name].label,
                    )

    def clean_aadhaar_number(self):
        value = self.cleaned_data.get("aadhaar_number", "")
        return normalise_aadhaar(value) if value else ""

    def duplicates(self, number: str):
        clash = type(self.instance).objects.filter(aadhaar_hash=crypto.keyed_hash(number))
        return clash.exclude(pk=self.instance.pk) if self.instance.pk else clash

    def clean(self):
        cleaned = super().clean()
        number = cleaned.get("aadhaar_number")
        if number and self.duplicates(number).exists():
            raise ValidationError({"aadhaar_number": self.duplicate_message})
        return cleaned

    def save(self, commit=True):
        for name, field in self.secret_inputs.items():
            if self.cleaned_data.get(field):
                self.instance.set_secret(name, self.cleaned_data[field])
        return super().save(commit)


class SensitiveAdminMixin:
    """Masked display, an audited reveal page, and the college passed to PersonForm."""

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        college = request.college

        class BoundForm(form):
            def __init__(self, *args, **kw):
                super().__init__(*args, college=college, **kw)

        return BoundForm

    def reveal_url_name(self) -> str:
        return f"{self.opts.app_label}_{self.opts.model_name}_reveal"

    def secret_display(self, obj, name: str) -> str:
        if obj is None or obj.pk is None or not obj.has_secret(name):
            return "not recorded"
        url = reverse(f"admin:{self.reveal_url_name()}", args=[obj.pk, name])
        shown = obj.masked(name) if name == "aadhaar" else "recorded"
        return format_html('{} <a href="{}">Reveal (audited)</a>', shown, url)

    @admin.display(description="Aadhaar on file")
    def aadhaar_on_file(self, obj):
        return self.secret_display(obj, "aadhaar")

    @admin.display(description="Certificate on file")
    def community_cert_on_file(self, obj):
        return self.secret_display(obj, "community_cert_no")

    def get_urls(self):
        reveal = path(
            "<int:pk>/reveal/<str:field>/",
            self.admin_site.admin_view(self.reveal_view),
            name=self.reveal_url_name(),
        )
        return [reveal, *super().get_urls()]

    def reveal_view(self, request, pk, field):
        obj = get_object_or_404(self.model.objects.all(), pk=pk)
        if field not in self.model.sensitive_fields:
            raise PermissionDenied
        value = obj.reveal(field, request.user)  # checks the permission and audits
        change = f"admin:{self.opts.app_label}_{self.opts.model_name}_change"
        return TemplateResponse(
            request,
            "admin/students/reveal.html",
            {
                **self.admin_site.each_context(request),
                "object": obj,
                "label": LABELS[field],
                "value": value,
                "back_url": reverse(change, args=[pk]),
            },
        )
