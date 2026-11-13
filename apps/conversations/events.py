"""
The events of the inbox: what wanps-core announces inside a process (a new message, a delivery
state, the bot of a chat) is sent to the group of the business that owns the account, through
the channel layer, so it reaches the members connected to any process.

An event must never stop what produced it: a message is saved even if nobody can be told.
"""

import functools
import json
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from wanps.inbox.services import serialize_message
from wanps.messaging.attachments import get_attachment
from wanps.messaging.models import Conversation, Message
from wanps.messaging.signals import message_status_updated

from apps.channels.models import ChannelAccount
from apps.channels.signals import client_block_changed

from .realtime import group_of
from .serializers import ChatMessageSerializer

logger = logging.getLogger(__name__)


def link_of(account_id):
    """The connection of an account to its business. Accounts without one tell nobody."""
    if account_id is None:
        return None
    return ChannelAccount.objects.filter(account_id=account_id).select_related("account").first()


def account_of(link) -> dict:
    return {"id": str(link.id), "name": link.account.name, "channel": link.account.channel}


def publish(link, payload: dict) -> None:
    """Send an event to the members of the business of `link`, once the data is committed."""
    payload = json.loads(json.dumps(payload, cls=DjangoJSONEncoder))

    def send():
        try:
            async_to_sync(get_channel_layer().group_send)(
                group_of(link.tenant_id), {"type": "inbox.event", "payload": payload}
            )
        except Exception:
            logger.exception("Could not send the event %s of the inbox", payload["type"])

    transaction.on_commit(send)


def never_raise(receiver_function):
    """An event is a courtesy: if it cannot be prepared, what produced it must go on."""

    @functools.wraps(receiver_function)
    def guarded(*args, **kwargs):
        try:
            return receiver_function(*args, **kwargs)
        except Exception:
            logger.exception("Could not prepare an event of the inbox")

    return guarded


def file_mark(message):
    attachment = get_attachment(message) if message.direction == Message.DIRECTION_IN else None
    if attachment is None:
        return None
    return {
        "kind": attachment.kind,
        "mime_type": attachment.mime_type,
        "filename": attachment.filename,
    }


@receiver(post_save)
@never_raise
def message_saved(sender, instance, created, **kwargs):
    # Every model sends this signal; wanps-core announces a message with it (also its proxies)
    if not created or not isinstance(instance, Message):
        return
    link = link_of(instance.account_id)
    if link is None:
        return
    message = ChatMessageSerializer({**serialize_message(instance), "file": file_mark(instance)})
    publish(
        link,
        {
            "type": "message.created",
            "account": account_of(link),
            "channel": instance.channel,
            "contact_id": instance.contact_id,
            "message": message.data,
        },
    )


@receiver(message_status_updated)
@never_raise
def message_status_changed(sender, message, status, **kwargs):
    link = link_of(message.account_id)
    if link is None:
        return
    publish(
        link,
        {
            "type": "message.status",
            "account": account_of(link),
            "channel": message.channel,
            "contact_id": message.contact_id,
            "message_id": message.pk,
            "status": status,
        },
    )


@receiver(post_save, sender=Conversation)
@never_raise
def bot_changed(sender, instance, created, **kwargs):
    # The record of a chat is created and then filled in; only the filled-in state is news
    link = link_of(instance.account_id)
    if created or link is None:
        return
    publish(
        link,
        {
            "type": "bot.changed",
            "account": account_of(link),
            "channel": instance.channel,
            "contact_id": instance.contact_id,
            "bot_paused": instance.bot_paused,
            "bot_paused_until": instance.bot_paused_until,
            "paused_by": instance.paused_by,
        },
    )


@receiver(client_block_changed)
@never_raise
def block_changed(sender, account, contact_id, blocked_until, **kwargs):
    """The bot started or stopped answering a client because of their faults. A block that ends by
    itself, when its time passes, sends nothing: `bot_blocked_until` tells when."""
    link = link_of(account.pk)
    if link is None:
        return
    publish(
        link,
        {
            "type": "block.changed",
            "account": account_of(link),
            "channel": account.channel,
            "contact_id": contact_id,
            "bot_blocked_until": blocked_until,
        },
    )
