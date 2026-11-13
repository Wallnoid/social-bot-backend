"""
The protection of the AI against clients who insist on messages unrelated to the business.

The AI calls the tool `flag_off_topic` when a message has nothing to do with the business. The server
counts the fault and answers with what the AI must tell the client: nothing yet, a warning with the
chances left, or that the client is blocked. After the last fault the client is blocked: the bot
does not answer and nothing is sent to the AI until the block ends. Only the bot is blocked, a
person can always answer.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .models import ClientStrikes
from .signals import client_block_changed, client_limit_changed, tenant_daily_limit_reached

logger = logging.getLogger(__name__)


def is_blocked(account, contact_id) -> bool:
    return ClientStrikes.objects.filter(
        account=account, contact_id=contact_id, blocked_until__gt=timezone.now()
    ).exists()


def hour_of_messages(account_id, contact_id):
    """The messages a client wrote to an account in the last hour, the oldest first."""
    from wanps.messaging.models import Message

    since = timezone.now() - timedelta(hours=1)
    lifted = (
        ClientStrikes.objects.filter(account_id=account_id, contact_id=contact_id)
        .values_list("messages_counted_from", flat=True)
        .first()
    )
    if lifted is not None:
        since = max(since, lifted)
    return Message.objects.filter(
        account_id=account_id,
        contact_id=contact_id,
        direction=Message.DIRECTION_IN,
        created_at__gte=since,
    ).order_by("created_at")


def limit_ends(account_id, contact_id, written) -> datetime | None:
    """
    When the client is under the limit again: when the oldest messages that put them over it leave
    the hour. None if they are not over it.
    """
    surplus = written - settings.BOT_MAX_MESSAGES_PER_HOUR
    if surplus < 1:
        return None
    oldest = list(
        hour_of_messages(account_id, contact_id).values_list("created_at", flat=True)[
            surplus - 1 : surplus
        ]
    )
    return oldest[0] + timedelta(hours=1) if oldest else None


def limited_untils(account_ids, contact_ids) -> dict:
    """
    For the chats of a page: until when the bot is silent with each client that wrote more messages
    in the last hour than it answers, as {(account, client): date}. The bot is silent with them
    without calling the AI; a person can always answer.
    """
    from django.db.models import Count
    from wanps.messaging.models import Message

    rows = (
        Message.objects.filter(
            account_id__in=account_ids,
            contact_id__in=contact_ids,
            direction=Message.DIRECTION_IN,
            created_at__gte=timezone.now() - timedelta(hours=1),
        )
        .values("account_id", "contact_id")
        .annotate(written=Count("id"))
        .filter(written__gt=settings.BOT_MAX_MESSAGES_PER_HOUR)
    )
    # The page asks for the few that look over the limit; a lifted limit makes the count smaller
    ends = {}
    for row in rows:
        key = (row["account_id"], row["contact_id"])
        ends[key] = limit_ends(*key, hour_of_messages(*key).count())
    return {key: value for key, value in ends.items() if value is not None}


def limited_until(account, contact_id):
    return limited_untils([account.pk], [contact_id]).get((account.pk, contact_id))


def check_flooding(account, contact_id) -> bool:
    """
    True when the client wrote more messages in the last hour than the bot answers, so the bot
    stays silent. It uses the saved messages: no table and no AI. It covers what the faults by topic
    do not: a hundred greetings are about the business, but they are still an abuse. The message
    that crosses the limit tells the team, once.
    """
    written = hour_of_messages(account.pk, contact_id).count()
    if written <= settings.BOT_MAX_MESSAGES_PER_HOUR:
        return False
    if written == settings.BOT_MAX_MESSAGES_PER_HOUR + 1:
        client_limit_changed.send(
            sender=check_flooding,
            account=account,
            contact_id=contact_id,
            limited_until=limit_ends(account.pk, contact_id, written),
        )
    return True


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


def next_midnight():
    """The start of the next day of the business: when its daily cap starts counting again."""
    zone = ZoneInfo(settings.BUSINESS_TIME_ZONE)
    tomorrow = timezone.now().astimezone(zone).date() + timedelta(days=1)
    return datetime.combine(tomorrow, datetime.min.time(), tzinfo=zone)


def replies_today(tenant) -> int:
    """The replies the bots of the business sent today, in all its accounts (no human author)."""
    from wanps.messaging.models import Message

    end = next_midnight()
    return Message.objects.filter(
        account__channel_account__tenant=tenant,
        direction=Message.DIRECTION_OUT,
        sent_by="",
        created_at__gte=end - timedelta(days=1),
        created_at__lt=end,
    ).count()


def daily_cap(tenant) -> int:
    own = tenant.bot_max_replies_per_day
    return settings.BOT_MAX_REPLIES_PER_DAY if own is None else own


def daily_limit_until(tenant):
    """Until when the bots of the business are silent because of its daily cap, or None."""
    if replies_today(tenant) < daily_cap(tenant):
        return None
    return next_midnight()


def check_daily_limit(account) -> bool:
    """
    True when the bots of the business of the account sent the replies of its day, so the bot stays
    silent and the AI is not called. The first time in a day tells the team.
    """
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.filter(channel_accounts__account=account).first()
    if tenant is None:
        return False
    until = daily_limit_until(tenant)
    if until is None:
        return False
    # Told once a day: `add` only works the first time, and the key forgets itself the next day
    if cache.add(f"daily-limit-told:{tenant.pk}:{until.date()}", 1, timeout=60 * 60 * 26):
        tenant_daily_limit_reached.send(
            sender=check_daily_limit, account=account, limited_until=until
        )
    return True
