"""
The bot hands a chat over to a person. The AI calls the tool `ask_for_a_person` when the client asks
for one, or has a complaint or a case the instructions do not cover: the bot pauses itself with no
end, the chat is marked as waiting, and the AI is told what to say to the client.
"""

from django.db import transaction
from django.utils import timezone
from wanps.messaging.models import Conversation

from .models import Handover
from .signals import handover_changed

INSTRUCTION = (
    "Tell the client, in their language, that a person from the business will take care of them "
    "soon, and say goodbye for now. Do not try to solve the case yourself."
)


@transaction.atomic
def ask_for_a_person(*, account, msg):
    """
    The tool: the bot stops answering this chat and the team sees that it waits for a person. The
    pause and the mark are saved together, so a chat is never paused with no mark.
    """
    Conversation.set_bot_paused(account, msg.contact_id, True, channel=msg.channel)
    row, created = Handover.objects.get_or_create(
        account=account, contact_id=msg.contact_id, defaults={"since": timezone.now()}
    )
    if created:
        handover_changed.send(
            sender=Handover, account=account, contact_id=msg.contact_id, since=row.since
        )
    return {"instruction": INSTRUCTION}


def waiting_sinces(chats) -> dict:
    """Since when each client of the chats waits for a person, as {(account, client): date}."""
    rows = Handover.objects.filter(
        account_id__in={chat["account"]["id"] for chat in chats},
        contact_id__in={chat["contact_id"] for chat in chats},
    )
    return {(row.account_id, row.contact_id): row.since for row in rows}


def waiting_since(account, contact_id):
    return waiting_sinces([{"account": {"id": account.pk}, "contact_id": contact_id}]).get(
        (account.pk, contact_id)
    )


def take_chat(account, contact_id) -> None:
    """A person took the chat (they replied or resumed the bot): it no longer waits."""
    deleted, _ = Handover.objects.filter(account=account, contact_id=contact_id).delete()
    if deleted:
        handover_changed.send(sender=Handover, account=account, contact_id=contact_id, since=None)
