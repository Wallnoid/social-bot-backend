"""
Admin configuration for the accounts app.

Customizes the Django admin panel for the User model.
"""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

User = get_user_model()


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin configuration for the User model."""

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
