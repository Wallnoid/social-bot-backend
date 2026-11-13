"""
The bot knowing who writes to it, what day and time it is and what was said before: a block of
context in its prompt, and two internal tools it can ask for. The AI is a scripted fake.
"""

import json
from datetime import UTC, datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from wanps.messaging.models import Message

from apps.channels.tests.test_bot import turn_on
from apps.channels.tests.test_bot_replies import client_writes
from apps.channels.tests.test_manage_accounts import add_account
from apps.channels.tests.test_tool_calls import ScriptedAI, asks_for
from apps.conversations.tests.test_inbox import add_message
from apps.conversations.tests.test_send import CLIENT, meta_replies
from apps.tenants.models import Tenant

pytestmark = pytest.mark.usefixtures("inline_processing_and_platform_ai", "no_real_meta_profiles")

GUAYAQUIL = ZoneInfo("America/Guayaquil")
FIXED_NOW = datetime(2026, 11, 13, 19, 35, tzinfo=UTC)  # a Friday, 14:35 in Guayaquil
CURRENT_TIME = "apps.channels.bot_context.current_time"


def bot_account(admin_client, tenant, meta_app, channel="whatsapp", number="111"):
    link = add_account(tenant, meta_app, number, channel=channel)
    assert turn_on(admin_client, link).status_code == 200
    return link


def writes(client, meta_app, ai, channel="whatsapp", number="111", now=FIXED_NOW, message_id=None):
    with (
        mock.patch("wanps.ai.handlers.provider_from_settings", return_value=ai),
        mock.patch(CURRENT_TIME, return_value=now),
        meta_replies(channel, message_id=f"reply-to-{message_id or 'first'}") as post,
    ):
        response = client_writes(client, meta_app, channel, number, message_id)
    assert response.status_code == 200
    return post


def earlier(link, text, ago, direction=Message.DIRECTION_IN, contact=CLIENT, now=None):
    """A message of the chat written `ago` before `now`."""
    message = add_message(link, contact, text, direction=direction)
    Message.objects.filter(pk=message.pk).update(created_at=(now or timezone.now()) - ago)
    return message


def local(moment):
    return moment.astimezone(GUAYAQUIL)


def test_the_prompt_tells_the_bot_the_client_the_business_and_the_time(
    admin_client, client, tenant, meta_app
):
    Tenant.objects.filter(pk=tenant.pk).update(
        industry=Tenant.Industry.HEALTH, description="We fix smiles in Quito."
    )
    bot_account(admin_client, tenant, meta_app)
    ai = ScriptedAI()

    writes(client, meta_app, ai)

    (prompt,) = ai.prompts
    assert "Acme Dental" in prompt
    assert "Salud y clínicas" in prompt
    assert "We fix smiles in Quito." in prompt
    assert "Ana" in prompt and "whatsapp" in prompt
    assert "Friday, 13 November 2026, 14:35" in prompt


@pytest.mark.parametrize(
    ("channel", "client_name"), [("whatsapp", "Ana"), ("messenger", None), ("instagram", None)]
)
def test_the_prompt_has_the_channel_and_says_when_the_name_of_the_client_is_not_known(
    admin_client, client, tenant, meta_app, channel, client_name
):
    bot_account(admin_client, tenant, meta_app, channel=channel)
    ai = ScriptedAI()

    writes(client, meta_app, ai, channel=channel)

    (prompt,) = ai.prompts
    assert channel in prompt
    if client_name:
        assert client_name in prompt
    else:
        assert "name unknown" in prompt
        assert "None" not in prompt


def test_the_time_follows_the_time_zone_setting(admin_client, client, tenant, meta_app, settings):
    settings.BUSINESS_TIME_ZONE = "UTC"
    bot_account(admin_client, tenant, meta_app)
    ai = ScriptedAI()

    writes(client, meta_app, ai)

    assert "Friday, 13 November 2026, 19:35" in ai.prompts[0]


def test_the_bot_can_look_up_the_file_of_the_client(admin_client, client, tenant, meta_app):
    link = bot_account(admin_client, tenant, meta_app)
    now = timezone.now()
    earlier(link, "first hello", timedelta(days=10), now=now)
    earlier(link, "we answered", timedelta(days=9), Message.DIRECTION_OUT, now=now)
    earlier(link, "last visit", timedelta(days=2), now=now)
    ai = ScriptedAI(asks_for("get_client_info"), "Welcome back, Ana.")

    writes(client, meta_app, ai, now=now)

    file = json.loads(ai.tool_results[1][0])
    assert file == {
        "name": "Ana",
        "channel": "whatsapp",
        "phone": CLIENT,
        "first_contact": local(now - timedelta(days=10)).date().isoformat(),
        "messages_exchanged": 4,
        "last_wrote_before_today": local(now - timedelta(days=2)).date().isoformat(),
    }


def test_the_phone_of_the_client_is_only_given_on_whatsapp(admin_client, client, tenant, meta_app):
    bot_account(admin_client, tenant, meta_app, channel="messenger")
    ai = ScriptedAI(asks_for("get_client_info"), "Hello.")

    writes(client, meta_app, ai, channel="messenger", now=timezone.now())

    file = json.loads(ai.tool_results[1][0])
    assert file["phone"] is None
    assert file["channel"] == "messenger"
    assert file["last_wrote_before_today"] is None


def test_the_bot_can_look_up_up_to_30_earlier_messages_in_order_and_never_the_current_one(
    admin_client, client, tenant, meta_app
):
    link = bot_account(admin_client, tenant, meta_app)
    now = timezone.now()
    for number in range(35):
        who = Message.DIRECTION_IN if number % 2 == 0 else Message.DIRECTION_OUT
        earlier(link, f"m{number:02d}", timedelta(hours=40 - number), who, now=now)
    ai = ScriptedAI(asks_for("get_previous_messages", limit=100), "Understood.")

    writes(client, meta_app, ai, now=now)

    found = json.loads(ai.tool_results[1][0])
    assert [item["text"] for item in found] == [f"m{number:02d}" for number in range(5, 35)]
    assert found[0]["from"] == "business" and found[1]["from"] == "client"
    assert found[0]["date"] == local(now - timedelta(hours=35)).strftime("%Y-%m-%d %H:%M")
    assert "Hi, are you open?" not in json.dumps(found)


def test_a_smaller_limit_gives_the_latest_messages(admin_client, client, tenant, meta_app):
    link = bot_account(admin_client, tenant, meta_app)
    now = timezone.now()
    for number in range(6):
        earlier(link, f"m{number}", timedelta(hours=10 - number), now=now)
    ai = ScriptedAI(asks_for("get_previous_messages", limit=2), "Ok.")

    writes(client, meta_app, ai, now=now)

    assert [item["text"] for item in json.loads(ai.tool_results[1][0])] == ["m4", "m5"]


def test_the_tools_only_show_the_chat_of_this_client_in_this_account(
    admin_client, client, tenant, meta_app
):
    link = bot_account(admin_client, tenant, meta_app)
    rival = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "222")
    now = timezone.now()
    earlier(link, "mine", timedelta(days=3), now=now)
    earlier(link, "another client", timedelta(days=3), contact="593990000099", now=now)
    earlier(rival, "same number, other business", timedelta(days=3), now=now)
    ai = ScriptedAI(asks_for("get_previous_messages"), asks_for("get_client_info"), "Ok.")

    writes(client, meta_app, ai, now=now)

    texts = [item["text"] for item in json.loads(ai.tool_results[1][0])]
    assert texts == ["mine"]
    file = json.loads(ai.tool_results[2][-1])
    assert file["messages_exchanged"] == 2  # "mine" and the one being answered
