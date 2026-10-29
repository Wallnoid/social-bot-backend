"""
Admin configuration for the tenants app.

Businesses are created here by the Social Bot team, together with their first
admin.
"""

from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model

from .models import Membership, Tenant

User = get_user_model()


class TenantCreateForm(forms.ModelForm):
    """Creation form: the business plus the data of its first admin."""

    admin_email = forms.EmailField(label="First admin email")
    admin_first_name = forms.CharField(max_length=150, label="First admin first name")
    admin_last_name = forms.CharField(max_length=150, label="First admin last name")

    class Meta:
        model = Tenant
        fields = ["name", "industry", "description"]

    def clean_admin_email(self):
        email = self.cleaned_data["admin_email"]
        existing = User.objects.filter(email__iexact=email).first()
        if existing is not None and not existing.is_active:
            raise forms.ValidationError(
                "This user is deactivated and cannot be the first admin."
            )
        return email


class MembershipInline(admin.TabularInline):
    """Read-only list of the members of a business."""

    model = Membership
    fields = ["user", "role"]
    readonly_fields = ["user", "role"]
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ["name", "created_at"]
    search_fields = ["name"]
    inlines = [MembershipInline]

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = TenantCreateForm
        return super().get_form(request, obj, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return super().get_fields(request, obj)
        return ["name", "industry", "description", "is_deleted", "deleted_at"]

    def get_inline_instances(self, request, obj=None):
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            return
        data = form.cleaned_data
        user = User.objects.filter(email__iexact=data["admin_email"]).first()
        if user is None:
            user = User.objects.create_user(
                email=data["admin_email"],
                first_name=data["admin_first_name"],
                last_name=data["admin_last_name"],
            )
        Membership.objects.create(tenant=obj, user=user, role=Membership.Role.ADMIN)
