"""
Admin configuration for the accounts app.

Customizes the Django admin panel for the User model.
"""

import logging

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm

from .emails import send_set_password_email

User = get_user_model()
logger = logging.getLogger(__name__)


class UserAdminChangeForm(UserChangeForm):
    """Edit form that keeps the optional username empty instead of failing."""

    username = forms.CharField(max_length=150, required=False, empty_value=None)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin configuration for the User model."""

    form = UserAdminChangeForm

    list_display = [
        "email",
        "first_name",
        "last_name",
        "is_active",
        "is_staff",
        "created_at",
    ]
    list_filter = [
        "is_active",
        "is_staff",
        "is_superuser",
        "created_at",
    ]
    search_fields = [
        "email",
        "first_name",
        "last_name",
        "username",
        "phone",
    ]
    ordering = ["-created_at"]

    # Fields shown when viewing/editing an existing user
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal Info",
            {
                "fields": (
                    "username",
                    "first_name",
                    "last_name",
                    "phone",
                    "bio",
                    "avatar",
                    "date_of_birth",
                ),
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (
            "Important dates",
            {"fields": ("last_login",)},
        ),
    )

    # Fields shown when creating a new user in admin
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    readonly_fields = ["created_at", "updated_at", "last_login"]
    actions = ["send_set_password_link"]

    @admin.action(description="Send set-password email")
    def send_set_password_link(self, request, queryset):
        """Email each selected active user a new link to create their password."""
        sent, skipped, failed = 0, 0, []
        for user in queryset:
            if not user.is_active:
                skipped += 1
                continue
            try:
                send_set_password_email(user)
            except Exception:
                logger.exception("Could not send set-password email to %s", user.pk)
                failed.append(user.email)
            else:
                sent += 1
        if sent:
            messages.success(request, f"Set-password email sent to {sent} user(s).")
        if skipped:
            messages.warning(request, f"Skipped {skipped} deactivated user(s).")
        if failed:
            messages.error(request, f"The email could not be sent to: {', '.join(failed)}.")
