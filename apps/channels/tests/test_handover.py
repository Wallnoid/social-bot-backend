"""
The bot hands the chat over to a person: the AI asks for one with an internal tool, the bot tells
the client and stops answering, and the inbox marks the chat until a person replies or someone
resumes the bot. The AI is a scripted fake.
"""

import json
from datetime import datetime, timedelta

import pytest
from django.utils import timezone
from wanps.messaging.models import Conversation

from apps.channels.tests.test_bot_context import bot_account, writes
from apps.channels.tests.test_tool_calls import ScriptedAI, asks_for
from apps.conversations.tests.test_inbox import inbox_url, messages_url
from apps.conversations.tests.test_send import CLIENT

pytestmark = pytest.mark.usefixtures(
    "inline_processing_and_platform_ai", "no_real_meta_profiles", "no_real_meta_sends"
)


@pytest.fixture
def link(admin_client, tenant, meta_app):
    return bot_account(admin_client, tenant, meta_app)


def listed(api):
    chats = api.get(inbox_url("whatsapp")).data["data"]["conversations"]
    return {chat["contact_id"]: chat for chat in chats}


def chat_of(api, link):
    return api.get(messages_url("whatsapp", CLIENT), {"account": str(link.id)}).data["data"]


def answers(post):
    return [c.kwargs["json"] for c in post.call_args_list if "text" in c.kwargs["json"]]


def asks_for_a_person(admin_client, client, meta_app):
    ai = ScriptedAI(asks_for("ask_for_a_person"), "A person from the team will help you soon.")
    post = writes(client, meta_app, ai)
    return ai, post


def test_when_the_ai_asks_for_a_person_the_bot_tells_the_client_and_the_chat_waits(
    admin_client, client, meta_app, link
):
    before = timezone.now()

    _, post = asks_for_a_person(admin_client, client, meta_app)

    assert [m["text"]["body"] for m in answers(post)] == [
        "A person from the team will help you soon."
    ]
    since = listed(admin_client)[CLIENT]["waiting_for_person_since"]
    assert since is not None
    assert before - timedelta(seconds=1) <= datetime.fromisoformat(since) <= timezone.now()
    assert chat_of(admin_client, link)["waiting_for_person_since"] is not None
    conversation = Conversation.objects.get(account=link.account, contact_id=CLIENT)
    assert conversation.bot_paused is True and conversation.bot_paused_until is None


def test_the_ai_is_told_to_tell_the_client_that_a_person_will_take_care_of_them(
    admin_client, client, meta_app, link
):
    ai, _ = asks_for_a_person(admin_client, client, meta_app)

    told = json.loads(ai.tool_results[1][0])["instruction"]
    assert "a person from the business will take care of them" in told


def test_the_next_messages_of_the_client_are_saved_without_calling_the_ai(
    admin_client, client, meta_app, link
):
    from wanps.messaging.models import Message

    asks_for_a_person(admin_client, client, meta_app)
    ai = ScriptedAI("The bot should be quiet.")

    post = writes(client, meta_app, ai, message_id="wamid.later")

    assert ai.prompts == []
    assert answers(post) == []
    assert Message.objects.filter(contact_id=CLIENT, direction=Message.DIRECTION_IN).count() == 2


def person_replies(admin_client, link):
    from apps.conversations.tests.test_send import meta_replies, send_url

    with meta_replies("whatsapp", message_id="wamid.person"):
        response = admin_client.post(
            send_url("whatsapp"), {"account": str(link.id), "text": "Hi, I am Ana."}, format="json"
        )
    assert response.status_code == 201
    return response


def test_a_reply_of_a_person_clears_the_mark_and_the_bot_waits_one_hour(
    admin_client, client, meta_app, link
):
    asks_for_a_person(admin_client, client, meta_app)
    before = timezone.now()

    person_replies(admin_client, link)

    assert listed(admin_client)[CLIENT]["waiting_for_person_since"] is None
    conversation = Conversation.objects.get(account=link.account, contact_id=CLIENT)
    assert conversation.bot_paused is True
    assert conversation.bot_paused_until is not None
    assert (
        before + timedelta(minutes=59)
        <= conversation.bot_paused_until
        <= timezone.now() + timedelta(minutes=61)
    )


def test_resuming_the_bot_clears_the_mark(admin_client, client, meta_app, link):
    from apps.conversations.tests.test_bot import set_bot

    asks_for_a_person(admin_client, client, meta_app)

    resumed = set_bot(admin_client, link, paused=False)

    assert resumed.status_code == 200
    assert listed(admin_client)[CLIENT]["waiting_for_person_since"] is None
    ai = ScriptedAI("I am back.")
    writes(client, meta_app, ai, message_id="wamid.after")
    assert len(ai.prompts) == 1


def test_the_mark_of_a_chat_is_not_shown_to_another_business(admin_client, client, meta_app, link):
    from apps.channels.tests.test_manage_accounts import add_account
    from apps.conversations.tests.test_inbox import add_message
    from apps.tenants.models import Membership, Tenant
    from apps.tenants.tests.helpers import add_member, client_for

    rival_tenant = Tenant.objects.create(name="Rival Clinic")
    rival = add_account(rival_tenant, meta_app, "222")
    add_message(rival, CLIENT, "Hi")
    rival_api = client_for(add_member(rival_tenant, "rival@rival.test", Membership.Role.ADMIN))

    asks_for_a_person(admin_client, client, meta_app)

    assert listed(admin_client)[CLIENT]["waiting_for_person_since"] is not None
    assert listed(rival_api)[CLIENT]["waiting_for_person_since"] is None
    assert chat_of(rival_api, rival)["waiting_for_person_since"] is None


def test_the_platform_rules_tell_the_ai_when_to_ask_for_a_person(client, meta_app, link):
    ai = ScriptedAI("Hello!")

    writes(client, meta_app, ai)

    rules = ai.prompts[0].split("Platform rules", 1)[1]
    assert "ask_for_a_person" in rules
    assert "talk to a person" in rules
    assert "complaint" in rules


def test_pausing_the_bot_for_a_while_takes_the_chat_and_clears_the_mark(
    admin_client, client, meta_app, link
):
    from apps.conversations.tests.test_bot import set_bot

    asks_for_a_person(admin_client, client, meta_app)

    paused = set_bot(admin_client, link, paused=True, minutes=30)

    assert paused.status_code == 200
    assert listed(admin_client)[CLIENT]["waiting_for_person_since"] is None


def test_a_pause_with_no_end_set_by_hand_on_a_waiting_chat_survives_a_reply(
    admin_client, client, meta_app, link
):
    from apps.conversations.tests.test_bot import set_bot

    asks_for_a_person(admin_client, client, meta_app)
    set_bot(admin_client, link, paused=True)

    person_replies(admin_client, link)

    conversation = Conversation.objects.get(account=link.account, contact_id=CLIENT)
    assert (conversation.bot_paused, conversation.bot_paused_until) == (True, None)
    assert listed(admin_client)[CLIENT]["waiting_for_person_since"] is None
