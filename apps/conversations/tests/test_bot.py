"""
Tests for pausing and resuming the bot in a conversation.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.generators import SchemaGenerator
from wanps.messaging.models import Account, App, Conversation, Message

from apps.channels.tests.test_connect_account import post_signed
from apps.channels.tests.test_disconnect_account import incoming
from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message, inbox_url, messages_url
from apps.conversations.tests.test_send import meta_replies, send_url
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

CLIENT = "593990000001"
OTHER_CLIENT = "593990000002"


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


def bot_url(channel, contact_id=CLIENT):
    return inbox_url(channel, contact_id, "bot")


def set_bot(api, link, paused, channel="whatsapp", contact_id=CLIENT, **extra):
    body = {"account": str(link.id), "paused": paused, **extra}
    return api.post(bot_url(channel, contact_id), body, format="json")


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_role_can_pause_the_bot_and_the_chat_shows_who_and_until_when(tenant, meta_app, role):
    link = add_account(tenant, meta_app, "111", name="Front desk")
    add_message(link, CLIENT, "Hola")
    member = client_for(
        add_member(tenant, "member@acme.test", role, first_name="Rosa", last_name="Vega")
    )
    before = timezone.now()

    response = set_bot(member, link, True, minutes=60)

    assert response.status_code == 200
    state = response.data["data"]
    assert set(state) == {
        "account",
        "channel",
        "contact_id",
        "bot_paused",
        "bot_paused_until",
        "paused_by",
    }
    assert state["account"] == {"id": str(link.id), "name": "Front desk", "channel": "whatsapp"}
    assert (state["channel"], state["contact_id"]) == ("whatsapp", CLIENT)
    assert (state["bot_paused"], state["paused_by"]) == (True, "Rosa Vega")
    until = parse_datetime(state["bot_paused_until"])
    assert before + timedelta(minutes=59) < until < timezone.now() + timedelta(minutes=61)
    # The chat shows it in its messages and in the list of chats
    chat = member.get(messages_url("whatsapp", CLIENT), {"account": str(link.id)}).data["data"]
    assert (chat["bot_paused"], chat["paused_by"]) == (True, "Rosa Vega")
    listed = member.get(inbox_url("whatsapp")).data["data"]["conversations"][0]
    assert listed["bot_paused"] is True


def turned_on_account(tenant, meta_app):
    """An account whose bot is on: it answers unless the chat is paused."""
    link = add_account(tenant, meta_app, "111")
    Account.objects.filter(pk=link.account_id).update(is_active=True)
    return link


def bot_is_called(client, meta_app, wamid, contact=CLIENT):
    """The client writes through the signed webhook; whether the bot was asked to reply."""
    payload = incoming("111", wamid)
    payload["entry"][0]["changes"][0]["value"]["messages"][0]["from"] = contact
    with mock.patch("wanps.messaging.dispatch.get_message_handler") as get_handler:
        response = post_signed(client, meta_app, payload)
    assert response.status_code == 200
    return get_handler.return_value.handle.called


def chat_state(api, link, channel="whatsapp", contact_id=CLIENT):
    return api.get(messages_url(channel, contact_id), {"account": str(link.id)}).data["data"]


def test_pausing_without_a_time_lasts_until_someone_resumes(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    add_message(link, CLIENT, "Hola")
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    response = set_bot(member, link, True)

    assert response.data["data"]["bot_paused"] is True
    assert response.data["data"]["bot_paused_until"] is None
    assert chat_state(member, link)["bot_paused"] is True


def test_a_paused_bot_does_not_reply_in_that_chat_but_the_messages_are_stored_and_other_chats_still_reply(
    tenant, meta_app, client
):
    link = turned_on_account(tenant, meta_app)
    add_message(link, CLIENT, "Hola")
    add_message(link, OTHER_CLIENT, "Hola")
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))
    assert bot_is_called(client, meta_app, "wamid.before-pausing") is True

    set_bot(member, link, True)

    assert bot_is_called(client, meta_app, "wamid.while-paused") is False
    assert Message.objects.filter(external_id="wamid.while-paused", account=link.account).exists()
    assert bot_is_called(client, meta_app, "wamid.other-chat", contact=OTHER_CLIENT) is True


def test_resuming_makes_the_bot_reply_again_and_clears_the_state(tenant, meta_app, client):
    link = turned_on_account(tenant, meta_app)
    add_message(link, CLIENT, "Hola")
    member = client_for(
        add_member(
            tenant, "member@acme.test", Membership.Role.AGENT, first_name="Rosa", last_name="Vega"
        )
    )
    # Replying as a person pauses the bot; so does pausing it by hand
    with meta_replies("whatsapp"):
        member.post(
            send_url("whatsapp"), {"account": str(link.id), "text": "Buenas"}, format="json"
        )
    assert chat_state(member, link)["bot_paused"] is True
    assert bot_is_called(client, meta_app, "wamid.paused-by-reply") is False

    response = set_bot(member, link, False)

    assert response.status_code == 200
    state = response.data["data"]
    assert (state["bot_paused"], state["bot_paused_until"], state["paused_by"]) == (False, None, "")
    assert chat_state(member, link)["bot_paused"] is False
    assert bot_is_called(client, meta_app, "wamid.after-resuming") is True


def test_a_pause_with_a_time_ends_by_itself(tenant, meta_app, client):
    link = turned_on_account(tenant, meta_app)
    add_message(link, CLIENT, "Hola")
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))
    set_bot(member, link, True, minutes=30)
    assert bot_is_called(client, meta_app, "wamid.within-the-time") is False

    # The 30 minutes go by
    Conversation.objects.filter(account=link.account).update(
        bot_paused_until=timezone.now() - timedelta(minutes=1)
    )

    assert chat_state(member, link)["bot_paused"] is False
    assert bot_is_called(client, meta_app, "wamid.after-the-time") is True


def test_an_account_of_another_business_a_disconnected_one_or_a_chat_that_does_not_exist_is_not_found_and_nothing_changes(
    tenant, meta_app
):
    mine = add_account(tenant, meta_app, "111")
    gone = add_account(tenant, meta_app, "222")
    on_messenger = add_account(tenant, meta_app, "333", channel="messenger")
    rival = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "444")
    for link in (mine, gone, on_messenger, rival):
        add_message(link, CLIENT, "Hola")
    admin = client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))
    admin.delete(f"/api/v1/channels/accounts/{gone.id}/")

    for link, contact in (
        (rival, CLIENT),
        (gone, CLIENT),
        (on_messenger, CLIENT),
        (mine, "593999999999"),
    ):
        assert set_bot(admin, link, True, contact_id=contact).status_code == 404
    assert not Conversation.objects.exists()


@pytest.mark.parametrize(
    "body_for",
    [
        lambda account: {"account": account, "paused": True, "minutes": 0},
        lambda account: {"account": account, "paused": True, "minutes": -5},
        lambda account: {"account": account, "paused": True, "minutes": 10081},
        lambda account: {"account": account, "paused": True, "minutes": "soon"},
        lambda account: {"account": account, "paused": True, "minutes": 1.5},
        lambda account: {"account": account},
        lambda account: {"account": account, "paused": "maybe"},
        lambda account: {"paused": True},
        lambda account: {"account": "not-an-id", "paused": True},
    ],
    ids=[
        "zero minutes",
        "negative minutes",
        "more than a week",
        "minutes not a number",
        "fractional minutes",
        "no paused",
        "paused not a boolean",
        "no account",
        "malformed account",
    ],
)
def test_an_invalid_time_or_body_is_rejected_and_nothing_changes(tenant, meta_app, body_for):
    link = add_account(tenant, meta_app, "111")
    add_message(link, CLIENT, "Hola")
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    response = member.post(bot_url("whatsapp"), body_for(str(link.id)), format="json")

    assert response.status_code == 400
    assert chat_state(member, link)["bot_paused"] is False
    assert not Conversation.objects.exists()


def test_api_docs_describe_pausing_and_resuming():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema["components"]["schemas"]
    path = "/api/v1/inbox/{channel}/conversations/{contact_id}/bot/"

    def named(ref):
        return components[ref["$ref"].rsplit("/", 1)[1]]

    operation = schema["paths"][path]["post"]
    body = named(operation["requestBody"]["content"]["application/json"]["schema"])
    assert set(body["properties"]) == {"account", "paused", "minutes"}
    assert body["properties"]["account"]["format"] == "uuid"
    assert body["properties"]["minutes"]["maximum"] == 10080
    assert set(body["required"]) == {"account", "paused"}

    ok = operation["responses"]["200"]["content"]["application/json"]["schema"]
    state = named(named(ok)["properties"]["data"])
    assert {"bot_paused", "bot_paused_until", "paused_by"} <= set(state["properties"])
    assert {"400", "404"} <= set(operation["responses"])
