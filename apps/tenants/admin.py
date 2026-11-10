"""
Admin configuration for the tenants app.

Businesses are created here by the Social Bot team, together with their first
admin. Later, the team can invite more people to a business from its edit page.
"""

import logging

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.accounts.emails import send_set_password_email

from .emails import send_invitation_email
from .models import Invitation, Membership, Tenant

User = get_user_model()
logger = logging.getLogger(__name__)


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
            raise forms.ValidationError("This user is deactivated and cannot be the first admin.")
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


class InvitationInlineForm(forms.ModelForm):
    """Invite a person to the business; the same checks as inviting through the API."""

    class Meta:
        model = Invitation
        fields = ["email", "role"]

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        tenant = self.instance.tenant
        if Membership.objects.filter(tenant=tenant, user__email__iexact=email).exists():
            raise forms.ValidationError("This person is already a member of this business.")
        if Invitation.pending().filter(tenant=tenant, email__iexact=email).exists():
            raise forms.ValidationError(
                "This email already has a pending invitation to this business."
            )
        if User.objects.filter(email__iexact=email, is_active=False).exists():
            raise forms.ValidationError("This user is deactivated and cannot be invited.")
        return email


class InvitationInlineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        emails = [
            form.cleaned_data["email"]
            for form in self.extra_forms
            if form.has_changed() and "email" in form.cleaned_data
        ]
        if len(emails) != len(set(emails)):
            raise forms.ValidationError("The same email is invited more than once.")


class InvitationInline(admin.TabularInline):
    """
    Pending invitations of a business. New rows invite a person by email;
    deleting a row cancels that invitation.
    """

    model = Invitation
    form = InvitationInlineForm
    formset = InvitationInlineFormSet
    fields = ["email", "role", "invited_by", "expires_at"]
    readonly_fields = ["invited_by", "expires_at"]
    extra = 0
    verbose_name = "pending invitation"
    verbose_name_plural = "pending invitations"

    def get_queryset(self, request):
        return super().get_queryset(request).filter(expires_at__gt=timezone.now())

    def has_change_permission(self, request, obj=None):
        # Sent invitations are only listed or cancelled, never edited
        return False


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ["name", "created_at"]
    search_fields = ["name"]
    inlines = [MembershipInline, InvitationInline]

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = TenantCreateForm
        return super().get_form(request, obj, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return super().get_fields(request, obj)
        return ["name", "industry", "description", "meta_app", "is_deleted", "deleted_at"]

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
        if not user.has_usable_password():
            try:
                send_set_password_email(user)
            except Exception:
                logger.exception("Could not send set-password email to %s", user.pk)
                messages.error(
                    request,
                    f"The business was created, but the email to {user.email} could not be sent.",
                )

    def save_formset(self, request, form, formset, change):
        if formset.model is not Invitation:
            return super().save_formset(request, form, formset, change)
        invitations = formset.save(commit=False)
        for cancelled in formset.deleted_objects:
            cancelled.soft_delete()
        for invitation in invitations:
            invitation.invited_by = request.user
            invitation.save()
            try:
                send_invitation_email(invitation)
            except Exception:
                logger.exception(
                    "Could not send invitation email for tenant %s", invitation.tenant_id
                )
                invitation.soft_delete()
                messages.error(
                    request,
                    f"The invitation email to {invitation.email} could not be sent, "
                    "so the invitation was cancelled.",
                )
