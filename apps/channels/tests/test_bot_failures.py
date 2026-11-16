"""
When the AI fails to answer a client: the team sees it in the inbox, the bot tries again a few times
within the hour, and the warning goes away when the bot or a person answers. The AI is a fake.
"""

from datetime import datetime, timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.channels.tests.test_bot_context import bot_account, writes
from apps.channels.tests.test_tool_calls import ScriptedAI
from apps.conversations.tests.test_inbox import inbox_url, messages_url
from apps.conversations.tests.test_send import CLIENT

pytestmark = pytest.mark.usefixtures("inline_processing_and_platform_ai", "no_real_meta_profiles")


class BrokenAI(ScriptedAI):
    """The AI is down: every call fails, as when the quota of the plan runs out."""

    def generate(self, context, system_prompt="", tools=None):
        self.prompts.append(system_prompt)
        raise RuntimeError("429 RESOURCE_EXHAUSTED")


@pytest.fixture
def link(admin_client, tenant, meta_app):
    return bot_account(admin_client, tenant, meta_app)


@pytest.fixture
def scheduled(settings):
    """The retries the bot schedules, instead of running them in a worker."""
    settings.CELERY_TASK_ALWAYS_EAGER = False
    with mock.patch("apps.channels.failures.retry_bot_reply.apply_async") as schedule:
        yield schedule


def answers(post):
    """The texts the bot sent to the client (marking the message as read is not an answer)."""
    return [call.kwargs["json"] for call in post.call_args_list if "text" in call.kwargs["json"]]


def listed(api):
    chats = api.get(inbox_url("whatsapp")).data["data"]["conversations"]
    return {chat["contact_id"]: chat for chat in chats}


def chat_of(api, link, contact=CLIENT):
    return api.get(messages_url("whatsapp", contact), {"account": str(link.id)}).data["data"]


def test_when_the_ai_fails_the_list_and_the_chat_show_since_when_the_bot_could_not_answer(
    admin_client, client, meta_app, link, scheduled
):
    before = timezone.now()

    post = writes(client, meta_app, BrokenAI())

    assert answers(post) == []
    shown = listed(admin_client)[CLIENT]["bot_failed_at"]
    assert shown is not None
    shown = datetime.fromisoformat(shown)
    assert before - timedelta(seconds=1) <= shown <= timezone.now()
    assert chat_of(admin_client, link)["bot_failed_at"] is not None


def test_a_failure_that_is_not_of_the_ai_shows_no_warning_and_is_not_retried(
    admin_client, client, meta_app, link, scheduled
):
    with mock.patch("apps.channels.handler.context_block", side_effect=RuntimeError("a bug")):
        writes(client, meta_app, ScriptedAI())

    assert listed(admin_client)[CLIENT]["bot_failed_at"] is None
    scheduled.assert_not_called()


def test_the_failure_of_a_client_is_not_shown_to_another_business(
    admin_client, client, meta_app, link, scheduled
):
    from apps.channels.tests.test_manage_accounts import add_account
    from apps.conversations.tests.test_inbox import add_message
    from apps.tenants.models import Membership, Tenant
    from apps.tenants.tests.helpers import add_member, client_for

    rival_tenant = Tenant.objects.create(name="Rival Clinic")
    rival = add_account(rival_tenant, meta_app, "222")
    add_message(rival, CLIENT, "Hi")
    rival_api = client_for(add_member(rival_tenant, "rival@rival.test", Membership.Role.ADMIN))

    writes(client, meta_app, BrokenAI())

    assert listed(admin_client)[CLIENT]["bot_failed_at"] is not None
    assert listed(rival_api)[CLIENT]["bot_failed_at"] is None
    assert chat_of(rival_api, rival)["bot_failed_at"] is None


def test_after_a_failure_the_bot_tries_again_at_1_5_15_and_30_minutes(
    client, meta_app, link, scheduled
):
    from wanps.messaging.models import Message

    from apps.channels.tasks import retry_bot_reply

    writes(client, meta_app, BrokenAI())
    message = Message.objects.get(contact_id=CLIENT, direction=Message.DIRECTION_IN)
    # Each retry fails again, until the four of them were used
    with mock.patch("wanps.ai.handlers.provider_from_settings", return_value=BrokenAI()):
        for _ in range(4):
            retry_bot_reply(message.pk)

    etas = [call.kwargs["eta"] - message.created_at for call in scheduled.call_args_list]
    assert [call.kwargs["args"] for call in scheduled.call_args_list] == [[message.pk]] * 4
    expected = [timedelta(minutes=minutes) for minutes in (1, 5, 15, 30)]
    assert all(
        abs(eta - want) < timedelta(seconds=2) for eta, want in zip(etas, expected, strict=True)
    )
    assert len(etas) == 4


def test_a_retry_answers_the_client_when_the_ai_is_back_and_the_warning_goes_away(
    admin_client, client, meta_app, link, scheduled
):
    from wanps.messaging.models import Message

    from apps.channels.tasks import retry_bot_reply
    from apps.conversations.tests.test_send import meta_replies

    writes(client, meta_app, BrokenAI())
    message = Message.objects.get(contact_id=CLIENT, direction=Message.DIRECTION_IN)

    with (
        mock.patch("wanps.ai.handlers.provider_from_settings", return_value=ScriptedAI("Hello!")),
        meta_replies("whatsapp", message_id="wamid.retry") as post,
    ):
        retry_bot_reply(message.pk)

    assert [sent["text"]["body"] for sent in answers(post)] == ["Hello!"]
    assert listed(admin_client)[CLIENT]["bot_failed_at"] is None


def test_a_new_message_of_the_client_cancels_the_retry(client, meta_app, link, scheduled):
    from wanps.messaging.models import Message

    from apps.channels.tasks import retry_bot_reply
    from apps.conversations.tests.test_inbox import add_message

    writes(client, meta_app, BrokenAI())
    message = Message.objects.get(contact_id=CLIENT, direction=Message.DIRECTION_IN)
    add_message(link, CLIENT, "Hello? Anyone there?")
    ai = ScriptedAI("An answer to the old message.")

    with mock.patch("wanps.ai.handlers.provider_from_settings", return_value=ai):
        retry_bot_reply(message.pk)

    assert ai.prompts == []


def test_a_reply_of_a_person_cancels_the_retry_and_clears_the_warning(
    admin_client, client, meta_app, link, scheduled
):
    from wanps.messaging.models import Message

    from apps.channels.tasks import retry_bot_reply
    from apps.conversations.tests.test_send import meta_replies, send_url

    writes(client, meta_app, BrokenAI())
    message = Message.objects.get(contact_id=CLIENT, direction=Message.DIRECTION_IN)
    with meta_replies("whatsapp", message_id="wamid.person"):
        reply = admin_client.post(
            send_url("whatsapp"), {"account": str(link.id), "text": "I am here"}, format="json"
        )
    ai = ScriptedAI("An answer the person already gave.")

    with mock.patch("wanps.ai.handlers.provider_from_settings", return_value=ai):
        retry_bot_reply(message.pk)

    assert reply.status_code == 201
    assert ai.prompts == []
    assert listed(admin_client)[CLIENT]["bot_failed_at"] is None


def test_no_retry_one_hour_after_the_message(client, meta_app, link, scheduled):
    from wanps.messaging.models import Message

    from apps.channels.tasks import retry_bot_reply

    writes(client, meta_app, BrokenAI())
    message = Message.objects.get(contact_id=CLIENT, direction=Message.DIRECTION_IN)
    # The worker was down and runs the retry late
    Message.objects.filter(pk=message.pk).update(created_at=timezone.now() - timedelta(minutes=61))
    ai = ScriptedAI("Too late.")

    with mock.patch("wanps.ai.handlers.provider_from_settings", return_value=ai):
        retry_bot_reply(message.pk)

    assert ai.prompts == []


def test_no_retry_while_the_bot_is_paused(client, meta_app, link, scheduled):
    from wanps.messaging.models import Conversation, Message

    from apps.channels.tasks import retry_bot_reply

    writes(client, meta_app, BrokenAI())
    message = Message.objects.get(contact_id=CLIENT, direction=Message.DIRECTION_IN)
    Conversation.set_bot_paused(link.account, CLIENT, True, paused_by="Ana", channel="whatsapp")
    ai = ScriptedAI("The bot should be quiet.")

    with mock.patch("wanps.ai.handlers.provider_from_settings", return_value=ai):
        retry_bot_reply(message.pk)

    assert ai.prompts == []


class FailsAfterATool(ScriptedAI):
    """The AI asks for a tool, and fails when it gets the result."""

    def generate(self, context, system_prompt="", tools=None):
        if self.prompts:
            self.prompts.append(system_prompt)
            raise RuntimeError("503 UNAVAILABLE")
        return super().generate(context, system_prompt, tools)


def the_message():
    from wanps.messaging.models import Message

    return Message.objects.get(contact_id=CLIENT, direction=Message.DIRECTION_IN)


def retry_with(ai, message):
    from apps.channels.tasks import retry_bot_reply

    with mock.patch("wanps.ai.handlers.provider_from_settings", return_value=ai):
        retry_bot_reply(message.pk)


def test_no_retry_when_the_account_was_turned_off_after_the_failure(
    client, meta_app, link, scheduled
):
    writes(client, meta_app, BrokenAI())
    link.account.is_active = False
    link.account.save(update_fields=["is_active"])
    ai = ScriptedAI("The account is off.")

    retry_with(ai, the_message())

    assert ai.prompts == []


def test_a_failure_after_a_tool_ran_shows_the_warning_but_is_not_retried(
    admin_client, client, meta_app, link, scheduled
):
    from apps.channels.models import ClientStrikes
    from apps.channels.tests.test_tool_calls import asks_for

    writes(client, meta_app, FailsAfterATool(asks_for("flag_off_topic")))

    assert listed(admin_client)[CLIENT]["bot_failed_at"] is not None
    scheduled.assert_not_called()
    assert ClientStrikes.objects.get().strikes == 1


def test_when_celery_runs_tasks_at_once_the_retry_is_not_scheduled(
    admin_client, client, meta_app, link, settings
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    ai = BrokenAI()

    with mock.patch("apps.channels.failures.retry_bot_reply.apply_async") as schedule:
        writes(client, meta_app, ai)

    schedule.assert_not_called()
    assert len(ai.prompts) == 1
    assert listed(admin_client)[CLIENT]["bot_failed_at"] is not None


def test_an_error_while_saving_the_failure_never_breaks_the_processing_of_the_message(
    client, meta_app, link, scheduled
):
    from wanps.messaging.dispatch import handle_message

    # The webhook already swallows every error; the worker and the retry run handle_message
    from apps.conversations.tests.test_inbox import add_message

    message = add_message(link, CLIENT, "Are you open?")
    with (
        mock.patch("wanps.ai.handlers.provider_from_settings", return_value=BrokenAI()),
        mock.patch(
            "apps.channels.failures.BotFailure.objects.select_for_update",
            side_effect=RuntimeError("database down"),
        ),
    ):
        handle_message(message)  # it does not raise


def test_an_error_while_clearing_the_warning_never_breaks_the_reply_of_a_person(
    admin_client, client, meta_app, link, scheduled
):
    from apps.conversations.tests.test_send import meta_replies, send_url

    writes(client, meta_app, BrokenAI())

    with (
        mock.patch("apps.channels.failures.clear_failure", side_effect=RuntimeError("db hiccup")),
        meta_replies("whatsapp", message_id="wamid.person"),
    ):
        reply = admin_client.post(
            send_url("whatsapp"), {"account": str(link.id), "text": "I am here"}, format="json"
        )

    assert reply.status_code == 201


def test_the_attempts_of_a_failure_are_counted_with_the_row_locked(
    client, meta_app, link, scheduled
):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as queries:
        writes(client, meta_app, BrokenAI())

    locked = [q["sql"] for q in queries if "botfailure" in q["sql"] and "FOR UPDATE" in q["sql"]]
    assert locked != []


def test_no_retry_of_a_message_that_was_already_handled(client, meta_app, link, scheduled):
    from wanps.messaging.models import Message

    writes(client, meta_app, BrokenAI())
    message = the_message()
    Message.objects.filter(pk=message.pk).update(processed=True)
    ai = ScriptedAI("Again?")

    retry_with(ai, message)

    assert ai.prompts == []
