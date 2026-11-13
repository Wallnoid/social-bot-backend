"""
The protection of the AI against clients who insist on unrelated messages: faults counted by a tool
that the AI calls, warnings written by the AI, and a temporary block that costs no AI. The AI is a
scripted fake.
"""

import json
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone
from wanps.messaging.models import Message

from apps.channels.models import ClientStrikes
from apps.channels.tests.test_bot_context import bot_account, earlier, writes
from apps.channels.tests.test_manage_accounts import add_account
from apps.channels.tests.test_tool_calls import ScriptedAI, asks_for
from apps.conversations.tests.test_send import CLIENT, meta_replies, send_url
from apps.tenants.models import Tenant

OTHER = "593990000002"

pytestmark = pytest.mark.usefixtures("inline_processing_and_platform_ai", "no_real_meta_profiles")


@pytest.fixture
def link(admin_client, tenant, meta_app):
    return bot_account(admin_client, tenant, meta_app)


def state(link, contact=CLIENT):
    return ClientStrikes.objects.filter(account=link.account, contact_id=contact).first()


def off_topic_messages(client, meta_app, count, first=0):
    """The client writes `count` messages and the AI flags each one. Returns the last tool answer."""
    answer = None
    for number in range(first, first + count):
        ai = ScriptedAI(asks_for("flag_off_topic"), "An answer.")
        writes(client, meta_app, ai, message_id=f"wamid.off-topic-{number}")
        answer = json.loads(ai.tool_results[1][0])
    return answer


def test_a_first_off_topic_message_counts_a_fault_without_a_warning(client, meta_app, link):
    answer = off_topic_messages(client, meta_app, 1)

    assert (answer["strikes"], answer["chances_left"]) == (1, 4)
    assert answer["warn"] is False and answer["blocked"] is False
    assert state(link).strikes == 1


def test_from_the_second_fault_the_ai_is_told_to_warn_with_the_chances_left(client, meta_app, link):
    answer = off_topic_messages(client, meta_app, 2)

    assert (answer["strikes"], answer["chances_left"]) == (2, 3)
    assert answer["warn"] is True and answer["blocked"] is False
    assert "3 chances" in answer["instruction"]


def test_the_last_fault_blocks_the_client_for_an_hour_and_tells_the_ai_to_say_so(
    client, meta_app, link
):
    before = timezone.now()

    answer = off_topic_messages(client, meta_app, 5)

    assert answer["blocked"] is True and answer["minutes"] == 60
    assert "60 minutes" in answer["instruction"]
    blocked_until = state(link).blocked_until
    assert before + timedelta(minutes=59) <= blocked_until <= timezone.now() + timedelta(minutes=61)


def test_while_blocked_the_bot_does_not_call_the_ai_and_the_messages_are_kept(
    client, meta_app, link
):
    ClientStrikes.objects.create(
        account=link.account,
        contact_id=CLIENT,
        blocked_until=timezone.now() + timedelta(minutes=30),
    )
    ai = ScriptedAI()

    post = writes(client, meta_app, ai)

    assert ai.prompts == []
    post.assert_not_called()
    assert Message.objects.filter(contact_id=CLIENT, direction=Message.DIRECTION_IN).count() == 1


def test_after_the_block_the_bot_answers_again(client, meta_app, link):
    ClientStrikes.objects.create(
        account=link.account, contact_id=CLIENT, blocked_until=timezone.now() - timedelta(minutes=1)
    )
    ai = ScriptedAI()

    post = writes(client, meta_app, ai)

    assert len(ai.prompts) == 1
    post.assert_called()


def test_the_faults_expire_after_a_day_without_new_ones(client, meta_app, link):
    ClientStrikes.objects.create(
        account=link.account,
        contact_id=CLIENT,
        strikes=4,
        last_strike_at=timezone.now() - timedelta(hours=25),
    )

    answer = off_topic_messages(client, meta_app, 1)

    assert answer["strikes"] == 1 and answer["blocked"] is False


def test_a_second_block_within_a_day_lasts_a_day(client, meta_app, link):
    ClientStrikes.objects.create(
        account=link.account,
        contact_id=CLIENT,
        strikes=4,
        last_strike_at=timezone.now() - timedelta(minutes=1),
        last_block_at=timezone.now() - timedelta(hours=2),
    )

    answer = off_topic_messages(client, meta_app, 1)

    assert answer["blocked"] is True and answer["minutes"] == 1440
    assert "24 hours" in answer["instruction"]


def test_the_faults_and_the_block_belong_to_one_client_in_one_account(
    client, meta_app, link, tenant
):
    rival = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "222")
    until = timezone.now() + timedelta(hours=1)
    ClientStrikes.objects.create(
        account=link.account, contact_id="593990000099", blocked_until=until
    )
    ClientStrikes.objects.create(account=rival.account, contact_id=CLIENT, blocked_until=until)
    ai = ScriptedAI(asks_for("flag_off_topic"), "An answer.")

    writes(client, meta_app, ai)

    assert len(ai.prompts) == 2  # the AI was called: this client is not blocked here
    assert state(link).strikes == 1
    assert state(link, "593990000099").strikes == 0
    assert state(rival).strikes == 0


def test_the_numbers_come_from_the_settings(client, meta_app, link, settings):
    settings.BOT_MAX_STRIKES = 3
    settings.BOT_WARN_FROM_STRIKE = 1
    settings.BOT_BLOCK_MINUTES = 10

    first = off_topic_messages(client, meta_app, 1)
    last = off_topic_messages(client, meta_app, 2, first=1)

    assert first["warn"] is True and first["chances_left"] == 2
    assert last["blocked"] is True and last["minutes"] == 10


def test_a_person_can_still_answer_a_blocked_client_and_that_does_not_lift_the_block(
    admin_client, meta_app, link
):
    until = timezone.now() + timedelta(minutes=30)
    ClientStrikes.objects.create(account=link.account, contact_id=CLIENT, blocked_until=until)
    earlier(link, "Hello?", timedelta(minutes=1))

    with meta_replies("whatsapp"):
        reply = admin_client.post(
            send_url("whatsapp"), {"account": str(link.id), "text": "I am here"}, format="json"
        )

    assert reply.status_code == 201
    assert state(link).blocked_until == until


def test_a_message_that_is_not_flagged_leaves_the_faults_alone(client, meta_app, link):
    ai = ScriptedAI(asks_for("get_client_info"), "An answer.")

    writes(client, meta_app, ai)

    assert state(link) is None


def test_an_error_while_counting_never_stops_the_bot_from_answering(client, meta_app, link):
    ai = ScriptedAI(asks_for("flag_off_topic"), "I could not check that.")

    with mock.patch("apps.channels.abuse.register_strike", side_effect=RuntimeError("boom")):
        post = writes(client, meta_app, ai)

    assert len(ai.prompts) == 2
    post.assert_called()


def flood(link, count, ago=timedelta(minutes=10), contact=CLIENT):
    for number in range(count):
        earlier(link, f"hi {number}", ago, contact=contact)


def test_a_client_who_writes_too_much_in_an_hour_gets_no_answer_and_no_ai(
    client, meta_app, link, settings
):
    settings.BOT_MAX_MESSAGES_PER_HOUR = 5
    flood(link, 5)  # with the new one, six in the hour
    ai = ScriptedAI()

    post = writes(client, meta_app, ai)

    assert ai.prompts == []
    post.assert_not_called()
    assert Message.objects.filter(contact_id=CLIENT, direction=Message.DIRECTION_IN).count() == 6


def test_the_limit_itself_is_still_answered(client, meta_app, link, settings):
    settings.BOT_MAX_MESSAGES_PER_HOUR = 5
    flood(link, 4)  # with the new one, exactly five
    ai = ScriptedAI()

    writes(client, meta_app, ai)

    assert len(ai.prompts) == 1


def test_messages_older_than_an_hour_do_not_count(client, meta_app, link, settings):
    settings.BOT_MAX_MESSAGES_PER_HOUR = 5
    flood(link, 30, ago=timedelta(minutes=61))
    ai = ScriptedAI()

    writes(client, meta_app, ai)

    assert len(ai.prompts) == 1


def test_only_the_messages_of_this_client_in_this_account_count(
    client, meta_app, link, settings, tenant
):
    settings.BOT_MAX_MESSAGES_PER_HOUR = 5
    rival = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "222")
    flood(link, 30, contact=OTHER)
    flood(rival, 30)
    ai = ScriptedAI()

    writes(client, meta_app, ai)

    assert len(ai.prompts) == 1


def test_the_answers_of_the_bot_and_the_team_do_not_count(client, meta_app, link, settings):
    settings.BOT_MAX_MESSAGES_PER_HOUR = 5
    for number in range(30):
        earlier(link, f"out {number}", timedelta(minutes=5), direction=Message.DIRECTION_OUT)
    ai = ScriptedAI()

    writes(client, meta_app, ai)

    assert len(ai.prompts) == 1


def test_a_person_can_still_answer_a_client_who_writes_too_much(
    admin_client, meta_app, link, settings
):
    settings.BOT_MAX_MESSAGES_PER_HOUR = 5
    flood(link, 10)

    with meta_replies("whatsapp"):
        reply = admin_client.post(
            send_url("whatsapp"), {"account": str(link.id), "text": "I am here"}, format="json"
        )

    assert reply.status_code == 201


def test_after_the_limit_is_lifted_the_bot_answers_and_counts_from_zero(
    client, meta_app, link, settings
):
    settings.BOT_MAX_MESSAGES_PER_HOUR = 5
    flood(link, 10)
    ClientStrikes.objects.create(
        account=link.account, contact_id=CLIENT, messages_counted_from=timezone.now()
    )
    ai = ScriptedAI()

    writes(client, meta_app, ai)

    assert len(ai.prompts) == 1
