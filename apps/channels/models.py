"""
Channel models.

wanps-core stores the Meta Apps and channel accounts and knows nothing about
businesses; these models record which business owns each account.
"""

from django.db import models
from django.db.models import Q, Value
from wanps.messaging.fields import EncryptedTextField

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


class ChannelTool(BaseModel):
    """
    A tool of the bot of an account: a GET to an address of the business or of a third party,
    which the AI may ask for while it answers a client. The key of the endpoint is stored
    encrypted and never returned by the API.
    """

    class AuthType(models.TextChoices):
        NONE = "none"
        BEARER = "bearer"
        HEADER = "header"

    account = models.ForeignKey("messaging.Account", on_delete=models.PROTECT, related_name="tools")
    name = models.CharField(max_length=64)
    description = models.TextField(help_text="What the tool is for, written for the AI.")
    url = models.CharField(max_length=500)
    parameters = models.JSONField(default=list, blank=True)
    auth_type = models.CharField(max_length=10, choices=AuthType.choices, default=AuthType.NONE)
    auth_header = models.CharField(max_length=64, blank=True, default="")
    auth_secret = EncryptedTextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta(BaseModel.Meta):
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "name"],
                condition=Q(is_deleted=False),
                name="channels_tool_name_unique_per_account",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.account})"


class ToolCall(models.Model):
    """
    One call the bot made to the endpoint of a tool. It keeps who and what was asked and how it
    went, never the path, the query, the keys or the answer: those can hold secrets or personal data.
    """

    class Status(models.TextChoices):
        OK = "ok"
        BLOCKED = "blocked"
        TIMEOUT = "timeout"
        TOO_LARGE = "too_large"
        HTTP_ERROR = "http_error"
        UNREACHABLE = "unreachable"
        REDIRECTS = "redirects"

    account = models.ForeignKey(
        "messaging.Account", on_delete=models.PROTECT, related_name="tool_calls"
    )
    tool = models.CharField(max_length=100)
    host = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.tool} → {self.host}: {self.status}"


class ClientStrikes(models.Model):
    """
    The faults of a client in an account (messages unrelated to the business) and, when they run
    out, until when the bot does not answer that client. It is state, not business data.
    """

    account = models.ForeignKey(
        "messaging.Account", on_delete=models.PROTECT, related_name="client_strikes"
    )
    contact_id = models.CharField(max_length=64)
    strikes = models.PositiveSmallIntegerField(default=0)
    last_strike_at = models.DateTimeField(null=True, blank=True)
    blocked_until = models.DateTimeField(null=True, blank=True)
    last_block_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "client strikes"
        constraints = [
            models.UniqueConstraint(
                fields=["account", "contact_id"], name="channels_one_strikes_row_per_client"
            ),
        ]

    def __str__(self):
        return f"{self.contact_id} in {self.account}: {self.strikes}"


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
