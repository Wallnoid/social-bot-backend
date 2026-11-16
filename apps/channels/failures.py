"""
When the AI fails to answer a client. The handler saves the failure of the chat, which the inbox
shows to the team, and schedules a few retries within the hour.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import BotFailure
from .signals import bot_failure_changed
from .tasks import retry_bot_reply
from .usage import record_usage

logger = logging.getLogger(__name__)


class AIUnavailableError(Exception):
    """
    The AI provider did not answer (quota, network, an error of the provider). `retry` is False
    when a tool already ran in that turn: trying again would run it again (and count a fault twice).
    """

    def __init__(self, reason: str, retry: bool = True):
        super().__init__(reason)
        self.retry = retry


class GuardedProvider:
    """
    The AI provider of a message, telling its errors apart from the rest of the bot: an error here
    is a failure the bot may try again. It counts the calls of the turn in `turns`.
    """

    def __init__(self, provider, turns: dict, key, account=None, tenant_id=None):
        self.provider = provider
        self.turns = turns
        self.key = key
        self.account = account
        self.tenant_id = tenant_id

    def generate(self, *args, **kwargs):
        calls = self.turns.get(self.key, 0)
        self.turns[self.key] = calls + 1
        try:
            response = self.provider.generate(*args, **kwargs)
        except Exception as exc:
            # After the first call of the turn, the AI already asked for tools that ran
            raise AIUnavailableError(type(exc).__name__, retry=calls == 0) from exc
        if self.account is not None:
            model = getattr(self.provider, "model", "")
            record_usage(self.account, self.tenant_id, model, response)
        return response

    def __getattr__(self, name):
        return getattr(self.provider, name)


def record_failure(msg, retry: bool = True) -> None:
    """
    Save that the bot could not answer the client of `msg`, and schedule the next attempt. It never
    raises: the warning is a help, and the processing of the message must end as usual.
    """
    try:
        save_failure(msg, retry)
    except Exception:
        logger.exception("Could not save the failure of the bot for message %s", msg.pk)


@transaction.atomic
def save_failure(msg, retry: bool) -> None:
    # The row is locked: two failures of the same client at once never lose an attempt
    row, created = BotFailure.objects.select_for_update().get_or_create(
        account=msg.account,
        contact_id=msg.contact_id,
        defaults={"message": msg, "failed_at": timezone.now()},
    )
    if created:
        bot_failure_changed.send(
            sender=BotFailure,
            account=msg.account,
            contact_id=msg.contact_id,
            failed_at=row.failed_at,
        )
    else:
        # The same message failed again, or a newer one of the client failed too
        row.attempts = row.attempts + 1 if row.message_id == msg.pk else 1
        row.message = msg
        row.save(update_fields=["attempts", "message"])
    delays = settings.BOT_RETRY_MINUTES
    # When Celery runs the tasks at once (local), the retry would run now, inside this one
    eager = getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)
    if retry and not eager and row.attempts <= len(delays):
        retry_bot_reply.apply_async(
            args=[msg.pk], eta=msg.created_at + timedelta(minutes=delays[row.attempts - 1])
        )


def failed_ats(chats) -> dict:
    """Since when the bot could not answer each client of the chats, as {(account, client): date}."""
    rows = BotFailure.objects.filter(
        account_id__in={chat["account"]["id"] for chat in chats},
        contact_id__in={chat["contact_id"] for chat in chats},
    )
    return {(row.account_id, row.contact_id): row.failed_at for row in rows}


def failed_at(account, contact_id):
    return failed_ats([{"account": {"id": account.pk}, "contact_id": contact_id}]).get(
        (account.pk, contact_id)
    )


def clear_failure(account_id, contact_id) -> None:
    rows = BotFailure.objects.filter(account_id=account_id, contact_id=contact_id)
    row = rows.select_related("account").first()
    if row is None:
        return
    rows.delete()
    bot_failure_changed.send(
        sender=BotFailure, account=row.account, contact_id=contact_id, failed_at=None
    )


@receiver(post_save)
def answered(sender, instance, created, **kwargs):
    """The bot or a person answered the chat: the warning goes away."""
    from wanps.messaging.models import Message

    # Every model sends this signal; wanps-core saves its messages also through proxies
    if not created or not isinstance(instance, Message):
        return
    if instance.direction != Message.DIRECTION_OUT:
        return
    # Saving the message must never fail because of the warning: the client already got it
    try:
        clear_failure(instance.account_id, instance.contact_id)
    except Exception:
        logger.exception("Could not clear the failure of the bot for message %s", instance.pk)
