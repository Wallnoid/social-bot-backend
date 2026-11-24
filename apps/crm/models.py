"""
CRM models.

A contact is a client of a business. For now there is one per chat: the client as one channel
account of the business sees them.
"""

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

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


def stage_was_deleted(stage_id):
    """
    Whether a stage was deleted while a contact was being put in it.

    Called right after saving the contact, in the same transaction: the save waits for an admin
    who is deleting the stage (deleting locks the stages), and once it is done this sees it.
    """
    return Stage.all_objects.filter(pk=stage_id, is_deleted=True).exists()


class Tag(BaseModel):
    """A label of a business to group its contacts (VIP, wholesaler...)."""

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="tags")
    name = models.CharField(max_length=50)

    class Meta(BaseModel.Meta):
        ordering = ["name"]
        constraints = [
            # One tag per name in a business, whatever the capitalization
            models.UniqueConstraint(
                Lower("name"),
                "tenant",
                condition=models.Q(is_deleted=False),
                name="crm_tag_one_per_name_in_business",
            ),
        ]

    def __str__(self):
        return self.name


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
    tags = models.ManyToManyField(Tag, blank=True, related_name="contacts")
    # The member of the business who takes care of the client; the link is the membership, so
    # a person who leaves the business stops being in charge (see `ContactSerializer`)
    assigned_to = models.ForeignKey(
        "tenants.Membership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="contacts_in_charge",
    )
    # Set when another contact absorbed this one (see `merge_contacts`): the row stays, deleted,
    # so its chat keeps finding the contact that has it now
    merged_into = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="merged_contacts"
    )
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


class Note(BaseModel):
    """An internal note the team writes on a contact; the clients never see it."""

    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="notes")
    # Who wrote it; a note outlives the account of its author
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    text = models.TextField()

    def __str__(self):
        return self.text[:50]


def merge_contacts(kept, absorbed):
    """
    Make `absorbed` part of `kept`: its notes, tags and chats pass to `kept`, which fills what it
    has empty with the data of `absorbed`, and `absorbed` is deleted pointing to `kept`.
    """
    for field in ("name", "phone", "email", "company"):
        if not getattr(kept, field):
            setattr(kept, field, getattr(absorbed, field))
    # A member who left the business is no longer in charge. The stage is not touched: the one of
    # `kept` stays, so this needs neither `lock_stages_of` nor `stage_was_deleted`
    if kept.assigned_to_id is None or kept.assigned_to.is_deleted:
        absorbed_in_charge = absorbed.assigned_to
        if absorbed_in_charge is not None and not absorbed_in_charge.is_deleted:
            kept.assigned_to = absorbed_in_charge
    kept.save(update_fields=["name", "phone", "email", "company", "assigned_to", "updated_at"])
    Note.all_objects.filter(contact=absorbed).update(contact=kept)
    kept.tags.add(*absorbed.tags.all())
    # The contacts absorbed before now belong to `kept`, so a chat is always one step away
    Contact.all_objects.filter(merged_into=absorbed).update(merged_into=kept)
    absorbed.merged_into = kept
    absorbed.save(update_fields=["merged_into", "updated_at"])
    absorbed.soft_delete()
