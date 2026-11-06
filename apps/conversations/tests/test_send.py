"""
Tests for replying to a conversation as a person. Only Meta is simulated: every
message goes out through `requests.post`.
"""

from datetime import timedelta
from unittest import mock

import pytest
import requests
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from wanps.messaging.models import Account, App, Message

from apps.channels.tests.test_manage_accounts import TOKEN, add_account
from apps.conversations.tests.test_inbox import add_message, inbox_url, messages_url
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

CLIENT = "593990000001"


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


def send_url(channel, contact_id=CLIENT):
    return inbox_url(channel, contact_id, "send")


def meta_replies(channel, message_id="sent-1"):
    """Meta accepts the message and answers like its API does on that channel."""
    body = (
        {"messages": [{"id": message_id}]} if channel == "whatsapp" else {"message_id": message_id}
    )
    response = mock.Mock(ok=True, status_code=200, content=b"{}", text="{}")
    response.json.return_value = body
    return mock.patch("requests.post", return_value=response)


def recipient_and_text(channel, payload):
    if channel == "whatsapp":
        return payload["to"], payload["text"]["body"]
    return payload["recipient"]["id"], payload["message"]["text"]


@pytest.mark.parametrize("channel", ["whatsapp", "messenger", "instagram"])
def test_a_member_sends_a_text_to_the_client_from_the_account_of_the_chat(
    tenant, meta_app, channel
):
    link = add_account(tenant, meta_app, "111", channel=channel)
    Account.objects.filter(pk=link.account_id).update(access_token="EAAG-this-account")
    add_message(link, CLIENT, "Hola")
    agent = client_for(add_member(tenant, "agent@acme.test", Membership.Role.AGENT))

    with meta_replies(channel) as post:
        response = agent.post(
            send_url(channel),
            {"account": str(link.id), "text": "Buenas tardes"},
            format="json",
        )

    assert response.status_code == 201
    post.assert_called_once()
    assert "EAAG-this-account" in str(post.call_args)
    assert recipient_and_text(channel, post.call_args.kwargs["json"]) == (CLIENT, "Buenas tardes")


def reply(api, link, text="Buenas tardes", channel="whatsapp"):
    with meta_replies(channel):
        return api.post(send_url(channel), {"account": str(link.id), "text": text}, format="json")


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_role_can_reply(tenant, meta_app, role):
    link = add_account(tenant, meta_app, "111")
    add_message(link, CLIENT, "Hola")
    member = client_for(add_member(tenant, "member@acme.test", role))

    assert reply(member, link).status_code == 201


@pytest.mark.parametrize(
    ("names", "shown"),
    [({"first_name": "Rosa", "last_name": "Vega"}, "Rosa Vega"), ({}, "member@acme.test")],
)
def test_the_sent_message_appears_in_the_chat_as_outgoing_with_the_members_name(
    tenant, meta_app, names, shown
):
    link = add_account(tenant, meta_app, "111")
    add_message(link, CLIENT, "Hola")
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT, **names))

    response = reply(member, link, text="Buenas tardes")

    sent = response.data["data"]
    assert (sent["direction"], sent["text"], sent["sent_by"]) == ("out", "Buenas tardes", shown)
    chat = member.get(messages_url("whatsapp", CLIENT), {"account": str(link.id)})
    last = chat.data["data"]["messages"][-1]
    assert (last["direction"], last["text"], last["sent_by"]) == ("out", "Buenas tardes", shown)


def test_sending_pauses_the_bot_in_that_chat(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    add_message(link, CLIENT, "Hola")
    add_message(link, "593990000002", "Otro chat")
    member = client_for(
        add_member(
            tenant, "member@acme.test", Membership.Role.AGENT, first_name="Rosa", last_name="Vega"
        )
    )

    reply(member, link)

    paused = member.get(messages_url("whatsapp", CLIENT), {"account": str(link.id)})
    other = member.get(messages_url("whatsapp", "593990000002"), {"account": str(link.id)})
    assert paused.data["data"]["bot_paused"] is True
    assert paused.data["data"]["paused_by"] == "Rosa Vega"
    assert other.data["data"]["bot_paused"] is False


def nothing_was_stored_or_paused(member, link):
    assert not Message.objects.filter(direction=Message.DIRECTION_OUT).exists()
    chat = member.get(messages_url("whatsapp", CLIENT), {"account": str(link.id)})
    assert chat.data["data"]["bot_paused"] is False


def test_a_closed_window_answers_conflict_and_sends_nothing(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    old = add_message(link, CLIENT, "Hola")
    Message.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=25))
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    with meta_replies("whatsapp") as post:
        response = member.post(
            send_url("whatsapp"), {"account": str(link.id), "text": "Hola de nuevo"}, format="json"
        )

    assert response.status_code == 409
    assert "24-hour" in response.data["message"]
    post.assert_not_called()
    nothing_was_stored_or_paused(member, link)


@pytest.mark.parametrize("failure", ["whatsapp rejects", "messenger rejects", "network down"])
def test_a_meta_rejection_answers_bad_gateway_and_stores_no_message(tenant, meta_app, failure):
    channel = "messenger" if failure.startswith("messenger") else "whatsapp"
    link = add_account(tenant, meta_app, "111", channel=channel)
    add_message(link, CLIENT, "Hola")
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))
    if failure == "network down":
        meta = mock.patch("requests.post", side_effect=requests.ConnectionError("down"))
    else:
        refusal = mock.Mock(ok=False, status_code=400, text='{"error": "secret-meta-detail"}')
        meta = mock.patch("requests.post", return_value=refusal)

    with meta:
        response = member.post(
            send_url(channel), {"account": str(link.id), "text": "Buenas"}, format="json"
        )

    assert response.status_code == 502
    assert "could not be delivered" in response.data["message"]
    assert "secret-meta-detail" not in str(response.data)
    assert not Message.objects.filter(direction=Message.DIRECTION_OUT).exists()
    chat = member.get(messages_url(channel, CLIENT), {"account": str(link.id)})
    assert chat.data["data"]["bot_paused"] is False


def test_an_account_of_another_business_or_a_disconnected_one_is_not_found_and_nothing_is_sent(
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

    for not_available in (rival, gone, on_messenger):
        with meta_replies("whatsapp") as post:
            response = admin.post(
                send_url("whatsapp"),
                {"account": str(not_available.id), "text": "Hola"},
                format="json",
            )
        assert response.status_code == 404
        post.assert_not_called()
    assert not Message.objects.filter(direction=Message.DIRECTION_OUT).exists()


@pytest.mark.parametrize(
    "body_for",
    [
        lambda account: {"account": account, "text": ""},
        lambda account: {"account": account, "text": "   "},
        lambda account: {"account": account},
        lambda account: {"account": "not-an-id", "text": "Hola"},
        lambda account: {"text": "Hola"},
    ],
    ids=["empty text", "blank text", "no text", "malformed account", "no account"],
)
def test_an_empty_or_missing_text_is_rejected_and_nothing_is_sent(tenant, meta_app, body_for):
    link = add_account(tenant, meta_app, "111")
    add_message(link, CLIENT, "Hola")
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    with meta_replies("whatsapp") as post:
        response = member.post(send_url("whatsapp"), body_for(str(link.id)), format="json")

    assert response.status_code == 400
    post.assert_not_called()
    assert not Message.objects.filter(direction=Message.DIRECTION_OUT).exists()


def test_api_docs_describe_sending():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema["components"]["schemas"]
    path = "/api/v1/inbox/{channel}/conversations/{contact_id}/send/"

    def named(ref):
        return components[ref["$ref"].rsplit("/", 1)[1]]

    operation = schema["paths"][path]["post"]
    body = named(operation["requestBody"]["content"]["application/json"]["schema"])
    assert set(body["properties"]) == {"account", "text"}
    assert body["properties"]["account"]["format"] == "uuid"

    created = operation["responses"]["201"]["content"]["application/json"]["schema"]
    sent = named(named(created)["properties"]["data"])
    assert {"direction", "text", "sent_by"} <= set(sent["properties"])
    assert not {"wa_message_id", "raw"} & set(sent["properties"])
    assert {"400", "404", "409", "502"} <= set(operation["responses"])
    assert "pauses the bot" in operation["description"]


def test_a_contact_with_no_chat_on_the_account_cannot_be_messaged(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    add_message(link, CLIENT, "Hola")
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    with meta_replies("whatsapp") as post:
        response = member.post(
            send_url("whatsapp", "593999999999"),
            {"account": str(link.id), "text": "Hola, ¿quién eres?"},
            format="json",
        )

    assert response.status_code == 409
    post.assert_not_called()
    assert not Message.objects.filter(direction=Message.DIRECTION_OUT).exists()


def test_a_failed_send_is_logged_without_the_error_text_or_secrets(tenant, meta_app, caplog):
    link = add_account(tenant, meta_app, "111", channel="messenger")
    add_message(link, CLIENT, "Hola")
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))
    down = requests.ConnectionError(
        f"Max retries exceeded with url: /messages?access_token={TOKEN}"
    )

    with mock.patch("requests.post", side_effect=down), caplog.at_level("WARNING"):
        member.post(
            send_url("messenger"), {"account": str(link.id), "text": "Buenas"}, format="json"
        )

    ours = [r for r in caplog.records if r.name == "apps.conversations.views"]
    assert len(ours) == 1
    assert "messenger" in ours[0].getMessage() and str(link.id) in ours[0].getMessage()
    assert "ConnectionError" in ours[0].getMessage()
    assert TOKEN not in caplog.text
