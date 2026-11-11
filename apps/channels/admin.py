"""
Admin configuration for the channels app.

The Social Bot team marks here which Meta App is the shared one and links the accounts to
their businesses. The Meta Apps (and their secrets) and the accounts themselves are made
in wanps-core's admin: Messaging for the apps, and one entry per channel for the accounts.
"""

from django import forms
from django.contrib import admin, messages
from django.db import transaction
from wanps.messaging.models import Account

from .models import ChannelAccount, SharedMetaApp, meta_app_for
from .services import disconnect


@admin.register(SharedMetaApp)
class SharedMetaAppAdmin(admin.ModelAdmin):
    list_display = ["app", "created_at"]


class ChannelAccountForm(forms.ModelForm):
    """Links an account that has no business yet to a business, like connecting it does."""

    class Meta:
        model = ChannelAccount
        fields = ["tenant", "account"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "account" in self.fields:
            # Also leaves out the archived accounts, whose old link is only soft-deleted
            self.fields["account"].queryset = Account.objects.filter(
                channel_account__isnull=True
            ).order_by("channel", "name")

    def clean(self):
        cleaned = super().clean()
        tenant, account = cleaned.get("tenant"), cleaned.get("account")
        if tenant and account and account.app_id != getattr(meta_app_for(tenant), "pk", None):
            # Meta sends the events of a business to its own Meta App, never to another
            self.add_error(
                "account", "This account uses another Meta App than the one of the business."
            )
        return cleaned


@admin.register(ChannelAccount)
class ChannelAccountAdmin(admin.ModelAdmin):
    form = ChannelAccountForm
    list_display = ["account", "tenant", "channel", "is_active", "created_at"]
    list_filter = ["tenant"]
    list_select_related = ["account", "tenant"]
    actions = ["disconnect"]

    @admin.display(description="Channel")
    def channel(self, link):
        return link.account.channel

    @admin.display(description="Active", boolean=True)
    def is_active(self, link):
        return link.account.is_active

    def get_readonly_fields(self, request, obj=None):
        # A link is not moved to another business or account; disconnect it and make a new one
        return ["tenant", "account"] if obj else []

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Disconnect the selected accounts")
    def disconnect(self, request, queryset):
        with transaction.atomic():
            for link in queryset.select_for_update().select_related("account"):
                disconnect(link)
        self.message_user(request, "Accounts disconnected.", messages.SUCCESS)
