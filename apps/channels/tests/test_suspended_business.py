"""
The bot of a suspended (or deleted) business: the messages of its clients are saved, but the bot
does not answer and the AI is not called, until the business is reactivated. The AI is a fake.
"""

from unittest import mock

import pytest
from django.utils import timezone
from wanps.messaging.models import Message

from apps.channels.tests.test_bot_context import bot_account, writes
from apps.channels.tests.test_tool_calls import ScriptedAI
from apps.conversations.tests.test_send import CLIENT, meta_replies
from apps.tenants.models import Tenant

pytestmark = pytest.mark.usefixtures(
    "inline_processing_and_platform_ai", "no_real_meta_profiles", "no_real_meta_sends"
)

CURRENT_URL = "/api/v1/tenants/current/"


@pytest.fixture
def link(admin_client, tenant, meta_app):
    return bot_account(admin_client, tenant, meta_app)


def suspend(tenant):
    Tenant.objects.filter(pk=tenant.pk).update(suspended_at=timezone.now())


def answers(post):
    return [c.kwargs["json"] for c in post.call_args_list if "text" in c.kwargs["json"]]


def test_the_bot_of_a_suspended_business_does_not_answer_and_no_ai_is_called(
    client, meta_app, link, tenant
):
    suspend(tenant)
    ai = ScriptedAI("Hello!")

    post = writes(client, meta_app, ai)

    assert ai.prompts == []
    assert answers(post) == []
    assert Message.objects.filter(contact_id=CLIENT, direction=Message.DIRECTION_IN).count() == 1


def test_the_bot_of_a_deleted_business_does_not_answer_either(client, meta_app, link, tenant):
    Tenant.objects.filter(pk=tenant.pk).update(is_deleted=True, deleted_at=timezone.now())
    ai = ScriptedAI("Hello!")

    writes(client, meta_app, ai)

    assert ai.prompts == []


def test_a_retry_of_a_suspended_business_does_not_answer(client, meta_app, link, tenant, settings):
    from apps.channels.tasks import retry_bot_reply

    class BrokenAI(ScriptedAI):
        def generate(self, *args, **kwargs):
            raise RuntimeError("503 UNAVAILABLE")

    settings.CELERY_TASK_ALWAYS_EAGER = False
    with mock.patch("apps.channels.failures.retry_bot_reply.apply_async"):
        writes(client, meta_app, BrokenAI())
    message = Message.objects.get(contact_id=CLIENT, direction=Message.DIRECTION_IN)
    suspend(tenant)
    ai = ScriptedAI("Hello again!")

    with (
        mock.patch("wanps.ai.handlers.provider_from_settings", return_value=ai),
        meta_replies("whatsapp", message_id="wamid.retry"),
    ):
        retry_bot_reply(message.pk)

    assert ai.prompts == []


def test_after_reactivating_the_bot_answers_and_the_members_get_in_again(
    admin_client, client, meta_app, link, tenant
):
    suspend(tenant)
    assert admin_client.get(CURRENT_URL).status_code == 403
    Tenant.objects.filter(pk=tenant.pk).update(suspended_at=None)
    ai = ScriptedAI("Welcome back!")

    post = writes(client, meta_app, ai)

    assert [m["text"]["body"] for m in answers(post)] == ["Welcome back!"]
    current = admin_client.get(CURRENT_URL)
    assert current.status_code == 200 and current.json()["data"]["name"] == "Acme Dental"
