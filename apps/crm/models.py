"""
CRM models.

A contact is a client of a business. For now there is one per chat: the client as one channel
account of the business sees them.
"""

from django.db import models

from apps.core.models import BaseModel

# The stages every business starts with, in order; the first one is where new contacts start
DEFAULT_STAGES = ["Nuevo", "En conversación", "Interesado", "Cliente", "Perdido"]


class Stage(BaseModel):
    """A stage of the pipeline of a business."""

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="stages")
    name = models.CharField(max_length=100)
    position = models.PositiveIntegerField(help_text="The order of the stage in the pipeline.")

    class Meta(BaseModel.Meta):
        ordering = ["position"]

    def __str__(self):
        return self.name


def first_stages(tenant_ids):
    """The first stage of the pipeline of each business, where its new contacts start."""
    first = {}
    stages = Stage.objects.filter(tenant_id__in=tenant_ids).order_by("-position")
    for tenant_id, stage_id in stages.values_list("tenant_id", "pk"):
        first[tenant_id] = stage_id
    return first


class Contact(BaseModel):
    """A client of a business, created by itself from the first message of a chat."""

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="contacts")
    # The wanps-core account, not the link to the business: the link is deleted when the account
    # is disconnected, and the client stays a client of the business.
    account = models.ForeignKey(
        "messaging.Account", on_delete=models.PROTECT, related_name="contacts"
    )
    external_id = models.CharField(
        max_length=64, help_text="The client on the channel of the account."
    )
    stage = models.ForeignKey(Stage, on_delete=models.PROTECT, related_name="contacts")
    # Written by the team; the name the channel gives is read from the chat, never saved here
    name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    company = models.CharField(max_length=255, blank=True)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["account", "external_id"], name="crm_contact_one_per_chat"
            ),
        ]

    def __str__(self):
        return f"{self.account} — {self.external_id}"
