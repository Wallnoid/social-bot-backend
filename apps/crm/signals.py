"""
Create the contact of a chat when its first message is saved.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from wanps.messaging.models import Message

from apps.channels.models import ChannelAccount
from apps.tenants.models import Tenant

from .models import DEFAULT_STAGES, Contact, Stage

logger = logging.getLogger(__name__)


@receiver(post_save)
def message_saved(sender, instance, created, **kwargs):
    # Every model sends this signal; wanps-core saves messages (also through its proxies)
    if not created or not isinstance(instance, Message) or instance.account_id is None:
        return
    # A message is saved even if its contact cannot be created; the savepoint keeps a database
    # error here from breaking the transaction of the message
    try:
        with transaction.atomic():
            # Also a disconnected account: its clients stay clients of the business
            link = ChannelAccount.all_objects.filter(account_id=instance.account_id).first()
            if link is None:
                return
            # Also the deleted ones: a chat keeps its one contact (whether to bring it back is
            # decided by the story that merges contacts)
            Contact.all_objects.get_or_create(
                account_id=instance.account_id,
                external_id=instance.contact_id,
                defaults={
                    "tenant_id": link.tenant_id,
                    # The first stage of the pipeline of the business, looked up only when
                    # the contact is created: get_or_create calls it then
                    "stage": lambda: Stage.objects.filter(tenant_id=link.tenant_id).first(),
                },
            )
    except Exception:
        logger.exception("Could not create the contact of a chat")


@receiver(post_save, sender=Tenant)
def tenant_saved(sender, instance, created, raw=False, **kwargs):
    # Every business starts with the default stages of the pipeline; one loaded from a fixture
    # brings its own
    if created and not raw:
        Stage.objects.bulk_create(
            Stage(tenant=instance, name=name, position=position)
            for position, name in enumerate(DEFAULT_STAGES)
        )
