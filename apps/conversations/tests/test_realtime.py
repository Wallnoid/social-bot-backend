"""
Tests for the inbox in real time: the connection permit, the permanent connection and the
events that reach the members of a business.

The permanent connection is opened through the real ASGI application; the events travel
through an in-memory channel layer and permits kept in memory (see conftest.py) instead of Redis.
"""

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from unittest import mock
from urllib.parse import urlsplit

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from asgiref.testing import ApplicationCommunicator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import caches
from rest_framework.test import APIClient
from wanps.messaging.models import App, Conversation, Message
from wanps.messaging.signals import message_status_updated

from apps.channels.abuse import register_strike
from apps.channels.models import ClientStrikes
from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.realtime import redeem_ticket
from apps.conversations.tests.test_inbox import add_message, inbox_url
from apps.conversations.tests.test_send import meta_replies, send_url
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for
from config.asgi import application

# The consumer closes its old database connections when it is done (as the web server does between
# requests), which would close the connection of a test running inside a transaction
pytestmark = pytest.mark.django_db(transaction=True)

User = get_user_model()

TICKET_URL = "/api/v1/inbox/ws-ticket/"


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


@pytest.mark.parametrize("role", Membership.Role.values)
def test_a_member_asks_for_a_connection_permit_for_the_active_business(tenant, role):
    member = client_for(add_member(tenant, "member@acme.test", role))

    response = member.post(TICKET_URL)

    assert response.status_code == 201
    data = response.data["data"]
    assert data["ticket"]
    assert 0 < data["expires_in"] <= 60
    # Every request gets its own permit
    assert member.post(TICKET_URL).data["data"]["ticket"] != data["ticket"]


def test_a_connection_permit_needs_a_signed_in_member():
    assert APIClient().post(TICKET_URL).status_code == 401


class Connection:
    """
    A browser's permanent connection, opened through the real ASGI application.

    A scenario runs entirely inside one `async_to_sync(...)`: the connection lives in a single
    event loop, and the database code of the consumer and of the test share one thread (and so
    one transaction). Anything synchronous in a scenario goes through `sync_to_async`.
    """

    def __init__(self, path):
        url = urlsplit(path)
        scope = {
            "type": "websocket",
            "path": url.path,
            "raw_path": url.path.encode(),
            "query_string": url.query.encode(),
            "headers": [],
            "subprotocols": [],
            "scheme": "ws",
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        }
        self.app = ApplicationCommunicator(application, scope)

    async def open(self) -> bool:
        await self.app.send_input({"type": "websocket.connect"})
        answer = await self.app.receive_output(timeout=2)
        return answer["type"] == "websocket.accept"

    async def receive(self) -> dict:
        answer = await self.app.receive_output(timeout=2)
        return json.loads(answer["text"])

    async def receives_nothing(self) -> bool:
        return await self.app.receive_nothing(timeout=0.2)

    async def close(self):
        await self.app.send_input({"type": "websocket.disconnect", "code": 1000})
        await self.app.wait(timeout=2)


async def open_connection(path):
    connection = Connection(path)
    return connection, await connection.open()


async def connect_as(member):
    """Ask for a permit as that member and open the connection with it."""
    answer = await sync_to_async(member.post)(TICKET_URL)
    return await open_connection(f"/ws/inbox/?ticket={answer.data['data']['ticket']}")


def test_connecting_with_a_valid_permit_joins_the_business(tenant):
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    async def scenario():
        connection, connected = await connect_as(member)
        await connection.close()
        return connected

    assert async_to_sync(scenario)() is True


def test_a_false_expired_used_or_missing_permit_rejects_the_connection(tenant):
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))
    used = member.post(TICKET_URL).data["data"]["ticket"]
    expired = member.post(TICKET_URL).data["data"]["ticket"]

    async def scenario():
        first, connected = await open_connection(f"/ws/inbox/?ticket={used}")
        assert connected is True
        await first.close()
        caches["ws_tickets"].clear()  # the permit is gone, as when its seconds run out
        return {
            path: (await open_connection(path))[1]
            for path in (
                f"/ws/inbox/?ticket={used}",
                f"/ws/inbox/?ticket={expired}",
                "/ws/inbox/?ticket=made-up",
                "/ws/inbox/?ticket=",
                "/ws/inbox/",
            )
        }

    assert set(async_to_sync(scenario)().values()) == {False}


# ---------------------------------------------------------------------------
# The events that reach a connected member
# ---------------------------------------------------------------------------


def add_agent(tenant, email="agent@acme.test"):
    return client_for(
        add_member(tenant, email, Membership.Role.AGENT, first_name="Rosa", last_name="Vega")
    )


def test_a_new_message_of_a_client_is_sent_to_the_members_of_the_business(tenant, meta_app):
    link = add_account(tenant, meta_app, "111", name="Front desk")
    first, second = add_agent(tenant, "a@acme.test"), add_agent(tenant, "b@acme.test")

    async def scenario():
        one, _ = await connect_as(first)
        two, _ = await connect_as(second)
        await sync_to_async(add_message)(link, "ana", "Hola")
        events = [await one.receive(), await two.receive()]
        await one.close()
        await two.close()
        return events

    for event in async_to_sync(scenario)():
        assert event["type"] == "message.created"
        assert event["account"] == {"id": str(link.id), "name": "Front desk", "channel": "whatsapp"}
        assert (event["channel"], event["contact_id"]) == ("whatsapp", "ana")
        message = event["message"]
        assert (message["text"], message["direction"], message["type"]) == ("Hola", "in", "text")
        assert message["file"] is None
        assert message["id"] and message["created_at"]


def test_a_change_of_delivery_state_is_sent(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    ours = add_message(link, "ana", "Buenas", direction=Message.DIRECTION_OUT)
    member = add_agent(tenant)

    async def scenario():
        connection, _ = await connect_as(member)
        await sync_to_async(message_status_updated.send)(
            sender=Message, message=ours, status="read"
        )
        event = await connection.receive()
        await connection.close()
        return event

    event = async_to_sync(scenario)()
    assert event["type"] == "message.status"
    assert event["account"]["id"] == str(link.id)
    assert (event["channel"], event["contact_id"]) == ("whatsapp", "ana")
    assert (event["message_id"], event["status"]) == (ours.pk, "read")


def test_pausing_or_resuming_the_bot_is_sent(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    add_message(link, "ana", "Hola")
    member = add_agent(tenant)

    async def scenario():
        connection, _ = await connect_as(member)
        await sync_to_async(member.post)(
            inbox_url("whatsapp", "ana", "bot"),
            {"account": str(link.id), "paused": True, "minutes": 60},
            format="json",
        )
        paused = await connection.receive()
        await sync_to_async(member.post)(
            inbox_url("whatsapp", "ana", "bot"),
            {"account": str(link.id), "paused": False},
            format="json",
        )
        resumed = await connection.receive()
        extra = await connection.receives_nothing()
        await connection.close()
        return paused, resumed, extra

    paused, resumed, extra = async_to_sync(scenario)()
    assert paused["type"] == resumed["type"] == "bot.changed"
    assert (paused["channel"], paused["contact_id"]) == ("whatsapp", "ana")
    assert paused["account"]["id"] == str(link.id)
    assert (paused["bot_paused"], paused["paused_by"]) == (True, "Rosa Vega")
    assert paused["bot_paused_until"]
    assert (resumed["bot_paused"], resumed["bot_paused_until"], resumed["paused_by"]) == (
        False,
        None,
        "",
    )
    # One event per change, not one for creating the record of the chat and another for its state
    assert extra is True


def test_nothing_of_another_business_is_received(tenant, meta_app):
    mine = add_account(tenant, meta_app, "111")
    rival_tenant = Tenant.objects.create(name="Rival Clinic")
    rival = add_account(rival_tenant, meta_app, "333")
    me, them = add_agent(tenant, "me@acme.test"), add_agent(rival_tenant, "them@rival.test")

    async def scenario():
        mine_connection, _ = await connect_as(me)
        rival_connection, _ = await connect_as(them)
        await sync_to_async(add_message)(rival, "rival-client", "Secret of the rival")
        theirs = await rival_connection.receive()
        saw_nothing = await mine_connection.receives_nothing()
        await sync_to_async(add_message)(mine, "ana", "Hola")
        ours = await mine_connection.receive()
        rival_saw_nothing = await rival_connection.receives_nothing()
        await mine_connection.close()
        await rival_connection.close()
        return theirs, saw_nothing, ours, rival_saw_nothing

    theirs, saw_nothing, ours, rival_saw_nothing = async_to_sync(scenario)()
    assert theirs["message"]["text"] == "Secret of the rival"
    assert ours["message"]["text"] == "Hola"
    assert saw_nothing is True and rival_saw_nothing is True


def test_a_message_without_a_business_account_is_ignored_without_failing(tenant):
    member = add_agent(tenant)

    async def scenario():
        connection, _ = await connect_as(member)
        # Single-business mode: the message has no account in the database
        await sync_to_async(Message.objects.create)(
            channel="whatsapp",
            external_id="no-account",
            contact_id="ana",
            direction=Message.DIRECTION_IN,
            message_type="text",
            text="Hola",
        )
        saw_nothing = await connection.receives_nothing()
        await connection.close()
        return saw_nothing

    assert async_to_sync(scenario)() is True
    assert Message.objects.filter(external_id="no-account").exists()


def test_a_failure_of_the_events_does_not_stop_the_message_from_being_saved(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    broken = mock.Mock()
    broken.group_send = mock.AsyncMock(side_effect=ConnectionError("redis is down"))

    with mock.patch("apps.conversations.events.get_channel_layer", return_value=broken):
        message = add_message(link, "ana", "Hola")

    assert Message.objects.filter(pk=message.pk).exists()


def test_a_reply_sent_from_the_api_reaches_the_other_connected_members(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    add_message(link, "ana", "Hola")
    sender, watcher = add_agent(tenant, "sender@acme.test"), add_agent(tenant, "watcher@acme.test")

    async def scenario():
        connection, _ = await connect_as(watcher)
        with meta_replies("whatsapp"):
            await sync_to_async(sender.post)(
                send_url("whatsapp", "ana"),
                {"account": str(link.id), "text": "Buenas tardes"},
                format="json",
            )
        event = await connection.receive()
        await connection.close()
        return event

    event = async_to_sync(scenario)()
    assert event["type"] == "message.created"
    message = event["message"]
    assert (message["direction"], message["text"], message["sent_by"]) == (
        "out",
        "Buenas tardes",
        "Rosa Vega",
    )


def test_api_docs_describe_the_connection_permit():
    from drf_spectacular.generators import SchemaGenerator

    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema["components"]["schemas"]

    operation = schema["paths"]["/api/v1/inbox/ws-ticket/"]["post"]
    response = operation["responses"]["201"]["content"]["application/json"]["schema"]
    named = lambda ref: components[ref["$ref"].rsplit("/", 1)[1]]  # noqa: E731
    ticket = named(named(response)["properties"]["data"])

    assert set(ticket["properties"]) == {"ticket", "expires_in"}


# ---------------------------------------------------------------------------
# What the code review found
# ---------------------------------------------------------------------------


def test_production_settings_keep_the_cache_of_the_connection_permits(tmp_path):
    # Settings load once per process, so production settings are read in a fresh one
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "REDIS_URL": "redis://localhost:6379/1",
    }
    result = subprocess.run(
        [sys.executable, "-c", "from django.conf import settings; print(sorted(settings.CACHES))"],
        cwd=settings.BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr[-500:]
    assert "ws_tickets" in result.stdout


@pytest.mark.parametrize("breaks", ["serializer", "lookup"])
def test_a_failure_while_preparing_an_event_does_not_break_what_produced_it(
    tenant, meta_app, caplog, breaks
):
    link = add_account(tenant, meta_app, "111")
    ours = add_message(link, "ana", "Buenas", direction=Message.DIRECTION_OUT)
    target = {
        "serializer": "apps.conversations.events.ChatMessageSerializer",
        "lookup": "apps.conversations.events.link_of",
    }[breaks]

    with mock.patch(target, side_effect=ValueError("boom")):
        message = add_message(link, "ana", "Hola")
        message_status_updated.send(sender=Message, message=ours, status="read")
        Conversation.set_bot_paused(link.account, "ana", True, channel="whatsapp")
        Conversation.set_bot_paused(link.account, "ana", False, channel="whatsapp")

    assert Message.objects.filter(pk=message.pk).exists()
    assert Conversation.objects.get(account=link.account, contact_id="ana").bot_paused is False
    assert "boom" in caplog.text


def test_a_deactivated_user_cannot_connect_even_with_a_permit(tenant):
    membership = add_member(tenant, "gone@acme.test", Membership.Role.AGENT)
    member = client_for(membership)
    ticket = member.post(TICKET_URL).data["data"]["ticket"]
    User.objects.filter(pk=membership.user_id).update(is_active=False)

    async def scenario():
        return (await open_connection(f"/ws/inbox/?ticket={ticket}"))[1]

    assert async_to_sync(scenario)() is False


def test_the_permit_is_redeemed_off_the_event_loop(tenant):
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))
    seen = []

    def spy(ticket):
        try:
            asyncio.get_running_loop()
            seen.append("on the event loop")
        except RuntimeError:
            seen.append("off the event loop")
        return redeem_ticket(ticket)

    async def scenario():
        with mock.patch("apps.conversations.consumers.redeem_ticket", spy):
            connection, connected = await connect_as(member)
        await connection.close()
        return connected

    assert async_to_sync(scenario)() is True
    assert seen == ["off the event loop"]


def test_the_channel_layer_does_not_cut_its_own_wait_for_messages():
    # An idle connection waits for a message in Redis for a few seconds at a time. redis-py 8 cuts
    # every read after 5 seconds unless told otherwise, which closed each socket after 5 seconds
    from channels_redis.core import RedisChannelLayer

    from config.settings import base

    host = base.CHANNEL_LAYERS["default"]["CONFIG"]["hosts"][0]

    assert isinstance(host, dict)
    assert host["socket_timeout"] > RedisChannelLayer.brpop_timeout


def add_supervisor(tenant, email="supervisor@acme.test"):
    return client_for(add_member(tenant, email, Membership.Role.SUPERVISOR))


def test_blocking_a_client_is_sent_to_the_members_with_until_when(tenant, meta_app, settings):
    settings.BOT_MAX_STRIKES = 1  # the first fault is the last one
    link = add_account(tenant, meta_app, "111")
    member = add_agent(tenant)

    async def scenario():
        connection, _ = await connect_as(member)
        await sync_to_async(register_strike)(link.account, "ana")
        event = await connection.receive()
        await connection.close()
        return event

    event = async_to_sync(scenario)()
    assert event["type"] == "block.changed"
    assert (event["channel"], event["contact_id"]) == ("whatsapp", "ana")
    assert event["account"]["id"] == str(link.id)
    sent = datetime.fromisoformat(event["bot_blocked_until"].replace("Z", "+00:00"))
    stored = ClientStrikes.objects.get().blocked_until
    assert abs(sent - stored) < timedelta(milliseconds=1)


def test_a_fault_that_does_not_block_sends_no_event(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    member = add_agent(tenant)

    async def scenario():
        connection, _ = await connect_as(member)
        await sync_to_async(register_strike)(link.account, "ana")
        saw_nothing = await connection.receives_nothing()
        await connection.close()
        return saw_nothing

    assert async_to_sync(scenario)() is True


def test_lifting_the_block_is_sent_with_no_date(tenant, meta_app, settings):
    settings.BOT_MAX_STRIKES = 1
    link = add_account(tenant, meta_app, "111")
    add_message(link, "ana", "Hola")
    register_strike(link.account, "ana")
    supervisor = add_supervisor(tenant)

    async def scenario():
        connection, _ = await connect_as(supervisor)
        await sync_to_async(supervisor.post)(
            inbox_url("whatsapp", "ana", "unblock"), {"account": str(link.id)}, format="json"
        )
        event = await connection.receive()
        extra = await connection.receives_nothing()
        await connection.close()
        return event, extra

    event, extra = async_to_sync(scenario)()
    assert event["type"] == "block.changed"
    assert (event["contact_id"], event["bot_blocked_until"]) == ("ana", None)
    assert extra is True


def test_lifting_a_block_that_was_not_on_sends_no_event(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    add_message(link, "ana", "Hola")
    supervisor = add_supervisor(tenant)

    async def scenario():
        connection, _ = await connect_as(supervisor)
        await sync_to_async(supervisor.post)(
            inbox_url("whatsapp", "ana", "unblock"), {"account": str(link.id)}, format="json"
        )
        saw_nothing = await connection.receives_nothing()
        await connection.close()
        return saw_nothing

    assert async_to_sync(scenario)() is True


def test_the_block_of_a_client_never_reaches_another_business(tenant, meta_app, settings):
    settings.BOT_MAX_STRIKES = 1
    mine = add_account(tenant, meta_app, "111")
    rival_tenant = Tenant.objects.create(name="Rival Clinic")
    add_account(rival_tenant, meta_app, "333")
    me, them = add_agent(tenant, "me@acme.test"), add_agent(rival_tenant, "them@rival.test")

    async def scenario():
        mine_connection, _ = await connect_as(me)
        rival_connection, _ = await connect_as(them)
        await sync_to_async(register_strike)(mine.account, "ana")
        ours = await mine_connection.receive()
        rival_saw_nothing = await rival_connection.receives_nothing()
        await mine_connection.close()
        await rival_connection.close()
        return ours, rival_saw_nothing

    ours, rival_saw_nothing = async_to_sync(scenario)()
    assert ours["type"] == "block.changed"
    assert rival_saw_nothing is True


def test_replying_as_a_person_sends_the_hour_in_which_the_bot_comes_back(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    add_message(link, "593990000001", "Hello?")
    member = add_agent(tenant)

    async def scenario():
        connection, _ = await connect_as(member)
        with meta_replies("whatsapp"):
            await sync_to_async(member.post)(
                send_url("whatsapp", "593990000001"),
                {"account": str(link.id), "text": "I am here"},
                format="json",
            )
        events = [await connection.receive(), await connection.receive()]
        await connection.close()
        return events

    events = async_to_sync(scenario)()
    bot = next(event for event in events if event["type"] == "bot.changed")
    assert bot["bot_paused"] is True
    assert bot["bot_paused_until"] is not None


def limited_scenario(tenant, meta_app, messages):
    """The client has written `messages` (limit 2); a member listens while the bot checks the last."""
    from apps.channels.abuse import check_flooding

    link = add_account(tenant, meta_app, "111")
    member = add_agent(tenant)
    for number in range(messages):
        add_message(link, "ana", f"Hola {number}")

    async def scenario():
        connection, _ = await connect_as(member)
        flooding = await sync_to_async(check_flooding)(link.account, "ana")
        events = []
        while not await connection.receives_nothing():
            events.append(await connection.receive())
        await connection.close()
        return flooding, events

    return link, async_to_sync(scenario)()


def test_crossing_the_message_limit_is_sent_with_until_when(tenant, meta_app, settings):
    settings.BOT_MAX_MESSAGES_PER_HOUR = 2

    link, (flooding, events) = limited_scenario(tenant, meta_app, 3)

    assert flooding is True
    event = events[-1]
    assert event["type"] == "limit.changed"
    assert (event["channel"], event["contact_id"]) == ("whatsapp", "ana")
    assert event["account"]["id"] == str(link.id)
    assert event["bot_limited_until"] is not None


@pytest.mark.parametrize("messages, flooding", [(2, False), (5, True)])
def test_the_limit_is_told_only_by_the_message_that_crosses_it(
    tenant, meta_app, settings, messages, flooding
):
    settings.BOT_MAX_MESSAGES_PER_HOUR = 2

    _, (answer, events) = limited_scenario(tenant, meta_app, messages)

    assert answer is flooding
    assert "limit.changed" not in [event["type"] for event in events]


def test_the_limit_of_a_client_never_reaches_another_business(tenant, meta_app, settings):
    from apps.channels.abuse import check_flooding

    settings.BOT_MAX_MESSAGES_PER_HOUR = 1
    mine = add_account(tenant, meta_app, "111")
    rival_tenant = Tenant.objects.create(name="Rival Clinic")
    add_account(rival_tenant, meta_app, "333")
    for number in range(2):
        add_message(mine, "ana", f"Hola {number}")
    me, them = add_agent(tenant, "me@acme.test"), add_agent(rival_tenant, "them@rival.test")

    async def scenario():
        mine_connection, _ = await connect_as(me)
        rival_connection, _ = await connect_as(them)
        await sync_to_async(check_flooding)(mine.account, "ana")
        ours = await mine_connection.receive()
        rival_saw_nothing = await rival_connection.receives_nothing()
        await mine_connection.close()
        await rival_connection.close()
        return ours, rival_saw_nothing

    ours, rival_saw_nothing = async_to_sync(scenario)()
    assert ours["type"] == "limit.changed"
    assert rival_saw_nothing is True


def test_lifting_the_limit_is_sent_with_no_date(tenant, meta_app, settings):
    settings.BOT_MAX_MESSAGES_PER_HOUR = 2
    link = add_account(tenant, meta_app, "111")
    for number in range(4):
        add_message(link, "ana", f"Hola {number}")
    supervisor = add_supervisor(tenant)

    async def scenario():
        connection, _ = await connect_as(supervisor)
        await sync_to_async(supervisor.post)(
            inbox_url("whatsapp", "ana", "unblock"), {"account": str(link.id)}, format="json"
        )
        event = await connection.receive()
        extra = await connection.receives_nothing()
        await connection.close()
        return event, extra

    event, extra = async_to_sync(scenario)()
    assert event["type"] == "limit.changed"
    assert (event["contact_id"], event["bot_limited_until"]) == ("ana", None)
    assert extra is True


def test_reaching_the_daily_cap_is_told_once_a_day_with_until_when(tenant, meta_app, settings):
    from apps.channels.abuse import check_daily_limit

    settings.BOT_MAX_REPLIES_PER_DAY = 2
    link = add_account(tenant, meta_app, "111")
    for number in range(2):
        add_message(link, "ana", f"Answer {number}", direction="out")
    member = add_agent(tenant)

    async def scenario():
        connection, _ = await connect_as(member)
        first = await sync_to_async(check_daily_limit)(link.account)
        event = await connection.receive()
        second = await sync_to_async(check_daily_limit)(link.account)
        extra = await connection.receives_nothing()
        await connection.close()
        return first, event, second, extra

    first, event, second, extra = async_to_sync(scenario)()
    assert (first, second, extra) == (True, True, True)
    assert event["type"] == "daily_limit.reached"
    assert event["bot_daily_limit_until"] is not None


def test_below_the_daily_cap_nothing_is_sent(tenant, meta_app, settings):
    from apps.channels.abuse import check_daily_limit

    settings.BOT_MAX_REPLIES_PER_DAY = 5
    link = add_account(tenant, meta_app, "111")
    add_message(link, "ana", "Answer", direction="out")
    member = add_agent(tenant)

    async def scenario():
        connection, _ = await connect_as(member)
        limited = await sync_to_async(check_daily_limit)(link.account)
        saw_nothing = await connection.receives_nothing()
        await connection.close()
        return limited, saw_nothing

    assert async_to_sync(scenario)() == (False, True)


def test_the_daily_cap_of_a_business_never_reaches_another_business(tenant, meta_app, settings):
    from apps.channels.abuse import check_daily_limit

    settings.BOT_MAX_REPLIES_PER_DAY = 1
    mine = add_account(tenant, meta_app, "111")
    add_message(mine, "ana", "Answer", direction="out")
    rival_tenant = Tenant.objects.create(name="Rival Clinic")
    add_account(rival_tenant, meta_app, "333")
    me, them = add_agent(tenant, "me@acme.test"), add_agent(rival_tenant, "them@rival.test")

    async def scenario():
        mine_connection, _ = await connect_as(me)
        rival_connection, _ = await connect_as(them)
        await sync_to_async(check_daily_limit)(mine.account)
        ours = await mine_connection.receive()
        rival_saw_nothing = await rival_connection.receives_nothing()
        await mine_connection.close()
        await rival_connection.close()
        return ours, rival_saw_nothing

    ours, rival_saw_nothing = async_to_sync(scenario)()
    assert ours["type"] == "daily_limit.reached"
    assert rival_saw_nothing is True
