"""
Channel models.

wanps-core stores the Meta Apps and channel accounts and knows nothing about
businesses; these models record which business owns each account.
"""

from django.db import models
from django.db.models import Q, Value

from apps.core.models import BaseModel


class ChannelAccount(BaseModel):
    """Links a wanps-core account (number, page or Instagram account) to its business."""

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.PROTECT, related_name="channel_accounts"
    )
    account = models.OneToOneField(
        "messaging.Account", on_delete=models.PROTECT, related_name="channel_account"
    )

    def __str__(self):
        return f"{self.account} ({self.tenant})"


class SharedMetaApp(BaseModel):
    """Marks the Meta App that businesses without their own app connect to."""

    # Not one-to-one: a deleted row keeps its app, and the same app can be marked again
    app = models.ForeignKey("messaging.App", on_delete=models.PROTECT, related_name="+")

    class Meta(BaseModel.Meta):
        verbose_name = "shared Meta App"
        constraints = [
            # A constant indexed once: a second row (not soft-deleted) is rejected
            models.UniqueConstraint(
                Value(True), condition=Q(is_deleted=False), name="channels_one_shared_meta_app"
            ),
        ]

    def __str__(self):
        return str(self.app)


def meta_app_for(tenant):
    """
    The Meta App a business connects its accounts to, or None if it has none active.

    A business with its own app uses only that one, even while it is inactive:
    Meta sends that business's events to its own app, never to the shared one.
    """
    if tenant.meta_app_id is not None:
        return tenant.meta_app if tenant.meta_app.is_active else None
    shared = SharedMetaApp.objects.select_related("app").filter(app__is_active=True).first()
    return shared.app if shared else None
