from django import forms
from django.contrib import admin, messages
from django.contrib.auth.forms import AdminPasswordChangeForm, ReadOnlyPasswordHashField

from apps.tenancy.admin import TenantModelAdmin

from . import links
from .models import RoleAssignment, User


class UserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(label="Repeat password", widget=forms.PasswordInput, strip=False)

    class Meta:
        model = User
        fields = ["username", "full_name", "email", "phone", "is_staff"]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            raise forms.ValidationError("The two passwords do not match.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(
        help_text="Passwords are not stored in plain text. Use the password form to change it."
    )

    class Meta:
        model = User
        fields = ["username", "full_name", "email", "phone", "is_active", "is_staff", "password"]


class RoleAssignmentInline(admin.TabularInline):
    model = RoleAssignment
    extra = 0
    fields = ["role", "department"]

    def get_queryset(self, request):
        # The parent user already limits rows; the manager adds the college filter.
        return RoleAssignment.objects.all()


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """College staff manage their own college's users. Platform users are managed by superusers."""

    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    change_user_password_template = None
    list_display = ["username", "full_name", "email", "is_active", "is_staff"]
    list_filter = ["is_active", "is_staff"]
    search_fields = ["username", "full_name", "email"]
    inlines = [RoleAssignmentInline]
    actions = ["send_invites"]

    def has_invite_permission(self, request) -> bool:
        return request.user.has_perm("accounts.invite_user")

    @admin.action(
        description="Send invite email (to set their first password)", permissions=["invite"]
    )
    def send_invites(self, request, queryset):
        sent = skipped = 0
        for user in queryset:
            if links.send_invite(user):
                sent += 1
            else:
                skipped += 1
        if sent:
            self.message_user(request, f"Sent {sent} invite email(s).", messages.SUCCESS)
        if skipped:
            self.message_user(
                request,
                f"Skipped {skipped}: no email address, inactive, or a password is already set "
                "(they can use “Forgot password?” on the login page).",
                messages.WARNING,
            )

    def get_queryset(self, request):
        # Users are not a TenantModel (platform staff have no college), so filter here.
        return super().get_queryset(request).filter(college=request.college)

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = self.add_form
        return super().get_form(request, obj, **kwargs)

    def get_inlines(self, request, obj):
        return self.inlines if request.college is not None and obj is not None else []

    def save_model(self, request, obj, form, change):
        if not change:
            obj.college = request.college
        super().save_model(request, obj, form, change)

    def get_urls(self):
        from django.urls import path

        return [
            path(
                "<id>/password/",
                self.admin_site.admin_view(self.user_change_password),
                name="accounts_user_password_change",
            ),
            *super().get_urls(),
        ]

    def user_change_password(self, request, id):
        from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

        return DjangoUserAdmin.user_change_password(self, request, id)


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(TenantModelAdmin):
    list_display = ["user", "role", "department", "created_at"]
    list_filter = ["role"]
    search_fields = ["user__username", "user__full_name"]
    autocomplete_fields = ["user"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user":
            kwargs["queryset"] = User.objects.filter(college=request.college)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
