"""
The protection of the AI against clients who insist on messages unrelated to the business.

The AI calls the tool `flag_off_topic` when a message has nothing to do with the business. The server
counts the fault and answers with what the AI must tell the client: nothing yet, a warning with the
chances left, or that the client is blocked. After the last fault the client is blocked: the bot
does not answer and nothing is sent to the AI until the block ends. Only the bot is blocked, a
person can always answer.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import ClientStrikes
from .signals import client_block_changed

logger = logging.getLogger(__name__)


def is_blocked(account, contact_id) -> bool:
    return ClientStrikes.objects.filter(
        account=account, contact_id=contact_id, blocked_until__gt=timezone.now()
    ).exists()


def duration(minutes: int) -> str:
    return f"{minutes} minutes" if minutes < 120 else f"{minutes // 60} hours"


@transaction.atomic
def register_strike(account, contact_id) -> dict:
    """
    Count a fault of the client and say what follows. The row is locked, so two messages of the same
    client at once never skip the limit. The faults expire after a time without new ones, and a client
    blocked again within that time is blocked for longer.
    """
    now = timezone.now()
    row, _ = ClientStrikes.objects.select_for_update().get_or_create(
        account=account, contact_id=contact_id
    )
    expire = timedelta(hours=settings.BOT_STRIKES_EXPIRE_HOURS)
    if row.last_strike_at is None or now - row.last_strike_at > expire:
        row.strikes = 0
    row.strikes += 1
    row.last_strike_at = now
    maximum = settings.BOT_MAX_STRIKES
    if row.strikes < maximum:
        row.save()
        return {
            "blocked": False,
            "strikes": row.strikes,
            "chances_left": maximum - row.strikes,
            "warn": row.strikes >= settings.BOT_WARN_FROM_STRIKE,
        }
    repeated = row.last_block_at is not None and now - row.last_block_at < expire
    minutes = settings.BOT_REPEAT_BLOCK_MINUTES if repeated else settings.BOT_BLOCK_MINUTES
    row.blocked_until = now + timedelta(minutes=minutes)
    row.last_block_at = now
    row.strikes = 0
    row.save()
    client_block_changed.send(
        sender=ClientStrikes,
        account=account,
        contact_id=contact_id,
        blocked_until=row.blocked_until,
    )
    return {
        "blocked": True,
        "strikes": maximum,
        "chances_left": 0,
        "warn": False,
        "minutes": minutes,
    }


def instruction_for(result: dict) -> str:
    """What the AI must do with the client, written for the AI."""
    if result["blocked"]:
        return (
            "Tell the client, in their language, that because they keep writing about things "
            "unrelated to the business you will not answer them for "
            f"{duration(result['minutes'])}, that a person from the business can still help "
            "them, and say goodbye."
        )
    if result["warn"]:
        return (
            "Tell the client, in their language, that this is unrelated to the business and "
            f"that they have {result['chances_left']} chances left before you stop answering "
            "them for a while. Then bring the conversation back to the business."
        )
    return (
        "Do not warn the client yet. Answer kindly in one sentence and bring the conversation "
        "back to the business."
    )


def flag_off_topic(*, account, msg):
    """The tool: count a fault of the client of the message and say what to tell them."""
    try:
        result = register_strike(account, msg.contact_id)
    except Exception as exc:
        # Counting is a protection: if it fails the bot must still answer
        logger.warning("Could not count a fault of a client (%s)", type(exc).__name__)
        return {"instruction": "Answer kindly and bring the conversation back to the business."}
    return {**result, "instruction": instruction_for(result)}
