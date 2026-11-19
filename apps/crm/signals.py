"""
Create the contact of a chat when its first message is saved.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from wanps.messaging.models import Message

from apps.channels.models import ChannelAccount

from .models import Contact

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
                defaults={"tenant_id": link.tenant_id},
            )
    except Exception:
        logger.exception("Could not create the contact of a chat")
