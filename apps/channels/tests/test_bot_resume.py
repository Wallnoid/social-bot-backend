"""
The bot taking the chat back by itself: a reply of a person pauses it for an hour, not for ever.
The AI and Meta are replaced by fakes.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone
from wanps.messaging.models import Conversation

from apps.channels.tests.test_bot import turn_on
from apps.channels.tests.test_bot_replies import client_writes
from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message, messages_url
from apps.conversations.tests.test_send import CLIENT, meta_replies, send_url

pytestmark = pytest.mark.usefixtures("inline_processing_and_platform_ai", "no_real_meta_profiles")


@pytest.fixture
def link(admin_client, tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    assert turn_on(admin_client, link).status_code == 200
    add_message(link, CLIENT, "Hi, are you open?")  # the client wrote: the window is open
    return link


@pytest.fixture
def ai():
    fake = mock.Mock()
    fake.generate.return_value = "Hello, I am the bot."
    with mock.patch("wanps.ai.handlers.provider_from_settings", return_value=fake):
        yield fake


def reply(api, link, message_id="sent-1", text="I will help you"):
    with meta_replies("whatsapp", message_id=message_id):
        response = api.post(
            send_url("whatsapp"), {"account": str(link.id), "text": text}, format="json"
        )
    assert response.status_code == 201
    return response


def conversation(link):
    return Conversation.objects.get(account=link.account, contact_id=CLIENT)


def assert_ends_in(moment, minutes, before, after):
    """`moment` is `minutes` after some instant between `before` and `after`."""
    assert (
        before + timedelta(minutes=minutes) - timedelta(seconds=2)
        <= moment
        <= after + timedelta(minutes=minutes) + timedelta(seconds=2)
    )


def test_replying_as_a_person_pauses_the_bot_for_an_hour_from_the_reply(admin_client, link):
    before = timezone.now()

    sent = reply(admin_client, link).data["data"]

    after = timezone.now()
    paused = conversation(link)
    assert paused.bot_paused is True
    assert paused.paused_by == sent["sent_by"] != ""
    assert_ends_in(paused.bot_paused_until, 60, before, after)


def test_the_chat_shows_until_when_the_bot_is_paused(admin_client, link):
    reply(admin_client, link)

    chat = admin_client.get(messages_url("whatsapp", CLIENT), {"account": str(link.id)})

    assert chat.data["data"]["bot_paused"] is True
    assert chat.data["data"]["bot_paused_until"] is not None


def test_each_new_reply_of_a_person_starts_the_hour_again(admin_client, link):
    reply(admin_client, link, message_id="sent-1")
    Conversation.objects.filter(pk=conversation(link).pk).update(
        bot_paused_until=timezone.now() + timedelta(minutes=5)
    )
    before = timezone.now()

    reply(admin_client, link, message_id="sent-2", text="Anything else?")

    assert_ends_in(conversation(link).bot_paused_until, 60, before, timezone.now())


def test_the_time_comes_from_the_setting(admin_client, link, settings):
    settings.BOT_RESUME_AFTER_MINUTES = 15
    before = timezone.now()

    reply(admin_client, link)

    assert_ends_in(conversation(link).bot_paused_until, 15, before, timezone.now())


def test_within_the_hour_the_bot_stays_silent(admin_client, client, meta_app, link, ai):
    reply(admin_client, link)
    Conversation.objects.filter(pk=conversation(link).pk).update(
        bot_paused_until=timezone.now() + timedelta(minutes=30)
    )

    with meta_replies("whatsapp") as post:
        client_writes(client, meta_app, "whatsapp", "111")

    ai.generate.assert_not_called()
    post.assert_not_called()


def test_after_the_hour_the_bot_answers_again(admin_client, client, meta_app, link, ai):
    reply(admin_client, link)
    # An hour and a minute later, as far as the bot can tell
    Conversation.objects.filter(pk=conversation(link).pk).update(
        bot_paused_until=timezone.now() - timedelta(minutes=1)
    )

    with meta_replies("whatsapp") as post:
        response = client_writes(client, meta_app, "whatsapp", "111")

    assert response.status_code == 200
    ai.generate.assert_called_once()
    assert post.call_args.kwargs["json"]["text"]["body"] == "Hello, I am the bot."
