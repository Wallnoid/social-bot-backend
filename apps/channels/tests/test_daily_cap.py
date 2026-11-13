"""
The daily cap of replies of the bots of a business: when they sent all the replies of the day, in all
its accounts, the bots stay silent and no AI is called until the next day. The AI is a scripted fake.
"""

from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from wanps.messaging.models import Message

from apps.channels.tests.test_bot_context import bot_account, earlier, writes
from apps.channels.tests.test_manage_accounts import add_account
from apps.channels.tests.test_tool_calls import ScriptedAI
from apps.conversations.tests.test_send import CLIENT
from apps.tenants.models import Tenant

pytestmark = pytest.mark.usefixtures("inline_processing_and_platform_ai", "no_real_meta_profiles")

OUT = Message.DIRECTION_OUT
CURRENT_URL = "/api/v1/tenants/current/"


@pytest.fixture
def link(admin_client, tenant, meta_app):
    return bot_account(admin_client, tenant, meta_app)


def bot_replies(link, count, ago=timedelta(minutes=1), sent_by="", prefix="bot"):
    for number in range(count):
        message = earlier(link, f"{prefix} {number}", ago, direction=OUT)
        Message.objects.filter(pk=message.pk).update(sent_by=sent_by)


def test_when_the_bots_sent_the_replies_of_the_day_the_bot_is_silent_and_no_ai_is_called(
    client, meta_app, link, settings
):
    settings.BOT_MAX_REPLIES_PER_DAY = 3
    bot_replies(link, 3)
    ai = ScriptedAI()

    post = writes(client, meta_app, ai)

    assert ai.prompts == []
    post.assert_not_called()
    assert Message.objects.filter(contact_id=CLIENT, direction=Message.DIRECTION_IN).count() == 1


def test_below_the_cap_the_bot_answers(client, meta_app, link, settings):
    settings.BOT_MAX_REPLIES_PER_DAY = 3
    bot_replies(link, 2)
    ai = ScriptedAI()

    writes(client, meta_app, ai)

    assert len(ai.prompts) == 1


def test_the_replies_of_yesterday_do_not_count(client, meta_app, link, settings):
    settings.BOT_MAX_REPLIES_PER_DAY = 3
    bot_replies(link, 10, ago=timedelta(days=1, minutes=1))
    ai = ScriptedAI()

    writes(client, meta_app, ai)

    assert len(ai.prompts) == 1


def test_the_replies_of_the_people_of_the_team_do_not_count(client, meta_app, link, settings):
    settings.BOT_MAX_REPLIES_PER_DAY = 3
    bot_replies(link, 10, sent_by="Ana Perez")
    ai = ScriptedAI()

    writes(client, meta_app, ai)

    assert len(ai.prompts) == 1


def test_the_messages_of_the_clients_do_not_count(client, meta_app, link, settings):
    settings.BOT_MAX_REPLIES_PER_DAY = 3
    for number in range(10):
        earlier(link, f"client {number}", timedelta(minutes=1), contact=f"5939900000{number:02d}")
    ai = ScriptedAI()

    writes(client, meta_app, ai)

    assert len(ai.prompts) == 1


def test_all_the_accounts_of_the_business_are_added_together(
    client, meta_app, link, settings, tenant
):
    settings.BOT_MAX_REPLIES_PER_DAY = 4
    second = add_account(tenant, meta_app, "222")
    bot_replies(link, 2)
    bot_replies(second, 2)
    ai = ScriptedAI()

    writes(client, meta_app, ai)

    assert ai.prompts == []


def test_the_replies_of_another_business_do_not_count(client, meta_app, link, settings):
    settings.BOT_MAX_REPLIES_PER_DAY = 3
    rival = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "333")
    bot_replies(rival, 20)
    ai = ScriptedAI()

    writes(client, meta_app, ai)

    assert len(ai.prompts) == 1


def test_a_business_with_its_own_cap_uses_it_instead_of_the_general_one(
    client, meta_app, link, settings, tenant
):
    settings.BOT_MAX_REPLIES_PER_DAY = 500
    Tenant.objects.filter(pk=tenant.pk).update(bot_max_replies_per_day=2)
    bot_replies(link, 2)
    ai = ScriptedAI()

    writes(client, meta_app, ai)

    assert ai.prompts == []


def test_a_business_with_a_higher_cap_keeps_answering(client, meta_app, link, settings, tenant):
    settings.BOT_MAX_REPLIES_PER_DAY = 2
    Tenant.objects.filter(pk=tenant.pk).update(bot_max_replies_per_day=100)
    bot_replies(link, 5)
    ai = ScriptedAI()

    writes(client, meta_app, ai)

    assert len(ai.prompts) == 1


def test_the_active_business_shows_until_when_the_cap_holds(admin_client, link, settings):
    settings.BOT_MAX_REPLIES_PER_DAY = 3
    assert admin_client.get(CURRENT_URL).data["data"]["bot_daily_limit_until"] is None
    bot_replies(link, 3)

    shown = admin_client.get(CURRENT_URL).data["data"]["bot_daily_limit_until"]

    assert shown is not None
    until = shown.astimezone(ZoneInfo(settings.BUSINESS_TIME_ZONE))
    # The next midnight of the business: within a day from now, and at the hour 00:00 there
    assert timezone.now() < until <= timezone.now() + timedelta(days=1)
    assert (until.hour, until.minute, until.second) == (0, 0, 0)
