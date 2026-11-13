"""
What the bot knows about who writes to it: a block of context for its prompt (the client, the
business and the time) and two read-only tools for what it needs only sometimes (the file of the
client and the earlier messages).

Everything is read from the account and the client of the message that is being answered: they come
from wanps-core, never from what the AI asks for, so the AI cannot look at anyone else's chat.
"""

from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from wanps.ai.tools import Tool
from wanps.messaging.models import Message

from .models import ChannelAccount

MAX_EARLIER_MESSAGES = 30
MAX_TEXT = 500
DATE_TIME = "%Y-%m-%d %H:%M"


def current_time():
    return timezone.now()


def business_zone():
    return ZoneInfo(settings.BUSINESS_TIME_ZONE)


def context_block(msg) -> str:
    """The client, the business and the time, as lines for the prompt."""
    lines = ["Context:"]
    link = ChannelAccount.objects.select_related("tenant").filter(account=msg.account).first()
    if link is not None:
        business = link.tenant.name
        if link.tenant.industry:
            business += f" ({link.tenant.get_industry_display()})"
        lines.append(f"- Business: {business}.")
        if link.tenant.description.strip():
            lines.append(f"- About the business: {link.tenant.description.strip()}")
    client = msg.contact_name.strip() or "name unknown"
    lines.append(f"- Client: {client}, writing on {msg.channel}.")
    now = current_time().astimezone(business_zone())
    lines.append(f"- Now: {now.strftime('%A, %d %B %Y, %H:%M')} ({settings.BUSINESS_TIME_ZONE}).")
    return "\n".join(lines)


def chat_of(account, msg):
    """The messages of this client in this account, and no others."""
    return Message.objects.filter(account=account, channel=msg.channel, contact_id=msg.contact_id)


def get_client_info(*, account, msg):
    chat = chat_of(account, msg)
    zone = business_zone()
    first = chat.order_by("created_at").first()
    start_of_today = current_time().astimezone(zone).replace(hour=0, minute=0, second=0)
    last_before_today = (
        chat.filter(direction=Message.DIRECTION_IN, created_at__lt=start_of_today)
        .order_by("-created_at")
        .first()
    )

    def day(message):
        return message.created_at.astimezone(zone).date().isoformat() if message else None

    return {
        "name": msg.contact_name.strip() or None,
        "channel": msg.channel,
        # On WhatsApp the number is who the client is; elsewhere the id means nothing to anyone
        "phone": msg.contact_id if msg.channel == "whatsapp" else None,
        "first_contact": day(first),
        "messages_exchanged": chat.count(),
        "last_wrote_before_today": day(last_before_today),
    }


def get_previous_messages(limit=MAX_EARLIER_MESSAGES, *, account, msg):
    try:
        limit = max(1, min(int(limit), MAX_EARLIER_MESSAGES))
    except (TypeError, ValueError):
        limit = MAX_EARLIER_MESSAGES
    zone = business_zone()
    earlier = (
        chat_of(account, msg)
        .filter(created_at__lte=msg.created_at)
        .exclude(pk=msg.pk)
        .order_by("-created_at")[:limit]
    )
    return [
        {
            "date": message.created_at.astimezone(zone).strftime(DATE_TIME),
            "from": "client" if message.direction == Message.DIRECTION_IN else "business",
            "text": message.text[:MAX_TEXT],
        }
        for message in reversed(list(earlier))
    ]


def internal_tools():
    """The tools every bot has, whatever its business."""
    return [
        Tool(
            get_client_info,
            name="get_client_info",
            description=(
                "The file of the client who is writing: name, channel, phone (WhatsApp only), "
                "date of the first contact, how many messages they have exchanged with the "
                "business and the last day they wrote before today. Use it to recognise a "
                "client who comes back."
            ),
            parameters_schema={"type": "object", "properties": {}},
        ),
        Tool(
            get_previous_messages,
            name="get_previous_messages",
            description=(
                "The earlier messages of this chat, oldest first, with their date and who wrote "
                "each one. Use it when the client refers to something said before that you do "
                "not remember."
            ),
            parameters_schema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "How many messages, from 1 to 30 (30 by default).",
                        "minimum": 1,
                        "maximum": MAX_EARLIER_MESSAGES,
                    }
                },
            },
        ),
    ]
