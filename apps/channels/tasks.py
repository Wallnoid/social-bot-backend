"""
Periodic jobs of the channels.
"""

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import ToolCall


@shared_task(ignore_result=True)
def delete_old_tool_calls() -> int:
    """Delete the records of the calls of the tools older than the retention time."""
    limit = timezone.now() - timedelta(days=settings.TOOL_CALL_RETENTION_DAYS)
    deleted, _ = ToolCall.objects.filter(created_at__lt=limit).delete()
    return deleted


@shared_task(ignore_result=True)
def retry_bot_reply(message_pk: int) -> None:
    """Try again to answer a message whose answer failed because of the AI."""
    from wanps.messaging.dispatch import handle_message
    from wanps.messaging.models import Message

    msg = Message.objects.select_related("account__app").filter(pk=message_pk).first()
    # Gone, already answered, or its account was turned off since the failure
    if msg is None or msg.processed or (msg.account is not None and not msg.account.is_active):
        return
    # An answer an hour late is no answer: the team sees the warning and answers by hand
    if timezone.now() - msg.created_at > timedelta(minutes=settings.BOT_RETRY_WINDOW_MINUTES):
        return
    # Only the last thing in the chat is answered: a newer message or a reply makes it old news
    latest = (
        Message.objects.filter(account=msg.account, contact_id=msg.contact_id, channel=msg.channel)
        .order_by("-created_at", "-pk")
        .first()
    )
    if latest is None or latest.pk != msg.pk:
        return
    handle_message(msg)
