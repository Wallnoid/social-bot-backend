"""
The bot of an account end to end: a client writes, the bot answers following the instructions the
business wrote, in the format of the channel. The AI and Meta are replaced by fakes.
"""

import hashlib
import hmac
import json
from unittest import mock

import pytest
from wanps.messaging.models import Account, Message

from apps.channels.tests.test_bot import INSTRUCTIONS, turn_on
from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_send import meta_replies, recipient_and_text

CLIENT = "593990000001"
REPLY = "Hello, I am the bot of Acme Dental."

pytestmark = pytest.mark.usefixtures("inline_processing_and_platform_ai", "no_real_meta_profiles")


class FakeAI:
    """Stands for the AI provider: remembers the instructions it was given and answers."""

    def __init__(self):
        self.prompts = []

    def generate(self, context, system_prompt="", tools=None):
        self.prompts.append(system_prompt)
        return REPLY


@pytest.fixture
def ai():
    fake = FakeAI()
    with mock.patch("wanps.ai.handlers.provider_from_settings", return_value=fake):
        yield fake


def webhook_payload(channel, external_id, message_id=None):
    if channel == "whatsapp":
        return {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "998877",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "metadata": {"phone_number_id": external_id},
                                "contacts": [{"wa_id": CLIENT, "profile": {"name": "Ana"}}],
                                "messages": [
                                    {
                                        "from": CLIENT,
                                        "id": message_id or "wamid.1",
                                        "type": "text",
                                        "text": {"body": "Hi, are you open?"},
                                        "timestamp": "1",
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    event = {
        "sender": {"id": CLIENT},
        "recipient": {"id": external_id},
        "timestamp": 1760000000000,
        "message": {"mid": message_id or "m_1", "text": "Hi, are you open?"},
    }
    obj = "page" if channel == "messenger" else "instagram"
    return {"object": obj, "entry": [{"id": external_id, "time": 1, "messaging": [event]}]}


def client_writes(client, meta_app, channel, external_id, message_id=None):
    body = json.dumps(webhook_payload(channel, external_id, message_id)).encode()
    signature = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
    return client.post(
        meta_app.webhook_path,
        body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
    )


def test_a_whatsapp_message_is_answered_following_the_instructions_of_the_account(
    admin_client, client, tenant, meta_app, ai
):
    link = add_account(tenant, meta_app, "111")
    assert turn_on(admin_client, link).status_code == 200

    with meta_replies("whatsapp") as post:
        response = client_writes(client, meta_app, "whatsapp", "111")

    assert response.status_code == 200
    assert ai.prompts and ai.prompts[0].startswith(INSTRUCTIONS)
    assert recipient_and_text("whatsapp", post.call_args.kwargs["json"]) == (CLIENT, REPLY)


@pytest.mark.parametrize(
    ("channel", "wanted", "unwanted"),
    [
        ("whatsapp", "*bold* with a single asterisk", "Write plain text"),
        ("messenger", "Write plain text", "*bold*"),
        ("instagram", "Write plain text", "*bold*"),
    ],
)
def test_the_prompt_asks_for_the_format_that_the_channel_shows(
    admin_client, client, tenant, meta_app, ai, channel, wanted, unwanted
):
    link = add_account(tenant, meta_app, "111", channel=channel)
    assert turn_on(admin_client, link).status_code == 200

    with meta_replies(channel):
        client_writes(client, meta_app, channel, "111")

    (prompt,) = ai.prompts
    assert wanted in prompt
    assert unwanted not in prompt


def test_a_bot_that_is_off_stores_the_message_and_does_not_answer(client, tenant, meta_app, ai):
    add_account(tenant, meta_app, "111")  # connected accounts start with the bot off

    with meta_replies("whatsapp") as post:
        response = client_writes(client, meta_app, "whatsapp", "111")

    assert response.status_code == 200
    assert Message.objects.filter(direction="in", contact_id=CLIENT).count() == 1
    post.assert_not_called()
    assert ai.prompts == []


def test_a_bot_that_is_on_without_instructions_stays_silent(client, tenant, meta_app, ai):
    # Turned on from the Django admin or the database, which the API rules do not cover
    link = add_account(tenant, meta_app, "111")
    Account.objects.filter(pk=link.account_id).update(is_active=True, system_prompt="")

    with meta_replies("whatsapp") as post:
        response = client_writes(client, meta_app, "whatsapp", "111")

    assert response.status_code == 200
    assert Message.objects.filter(direction="in", contact_id=CLIENT).count() == 1
    post.assert_not_called()
    assert ai.prompts == []
