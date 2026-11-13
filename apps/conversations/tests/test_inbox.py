"""
Tests for the inbox: the conversations and messages of a business, one inbox per
channel.
"""

import pytest
from drf_spectacular.generators import SchemaGenerator
from wanps.messaging.models import App, Conversation, Message

from apps.channels.tests.test_manage_accounts import add_account
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


def inbox_url(channel, *parts):
    return "/api/v1/inbox/" + "/".join([channel, "conversations", *parts]) + "/"


def add_message(link, contact_id, text, direction=Message.DIRECTION_IN, contact_name="Ana"):
    """A stored message of a connected account."""
    return Message.objects.create(
        channel=link.account.channel,
        account_id=link.account_id,
        external_id=f"wamid.{link.account_id}.{contact_id}.{text}",
        contact_id=contact_id,
        contact_name=contact_name,
        direction=direction,
        message_type="text",
        text=text,
    )


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_member_lists_the_chats_of_a_channel_of_their_business(tenant, meta_app, role):
    link = add_account(tenant, meta_app, "111", name="Front desk")
    add_message(link, "593990000001", "Hola", contact_name="Ana")
    add_message(link, "593990000002", "Buenas", contact_name="Luis")
    Conversation.set_bot_paused(link.account, "593990000002", True, channel="whatsapp")
    member_client = client_for(add_member(tenant, "member@acme.test", role))

    response = member_client.get(inbox_url("whatsapp"))

    assert response.status_code == 200
    data = response.data["data"]
    assert data["has_more"] is False
    by_contact = {chat["contact_id"]: chat for chat in data["conversations"]}
    ana, luis = by_contact["593990000001"], by_contact["593990000002"]
    assert set(ana) == {
        "account",
        "channel",
        "contact_id",
        "contact_name",
        "last_message",
        "window_open",
        "bot_paused",
        "bot_paused_until",
        "paused_by",
        "bot_blocked_until",
    }
    assert ana["account"] == {"id": str(link.id), "name": "Front desk", "channel": "whatsapp"}
    assert (ana["channel"], ana["contact_name"], ana["window_open"]) == ("whatsapp", "Ana", True)
    assert set(ana["last_message"]) == {
        "id",
        "direction",
        "type",
        "text",
        "status",
        "sent_by",
        "created_at",
    }
    assert (ana["last_message"]["text"], ana["last_message"]["direction"]) == ("Hola", "in")
    assert ana["bot_paused"] is False
    assert luis["bot_paused"] is True


def contacts_of(response):
    return [chat["contact_id"] for chat in response.data["data"]["conversations"]]


def test_the_list_never_mixes_channels_or_businesses(tenant, meta_app):
    mine_whatsapp = add_account(tenant, meta_app, "111", channel="whatsapp")
    mine_messenger = add_account(tenant, meta_app, "222", channel="messenger")
    rival = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "333")
    add_message(mine_whatsapp, "ana", "Hola")
    add_message(mine_messenger, "mia", "Hola")
    add_message(rival, "rival-client", "Hola")
    admin = client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))

    assert contacts_of(admin.get(inbox_url("whatsapp"))) == ["ana"]
    assert contacts_of(admin.get(inbox_url("messenger"))) == ["mia"]


def test_the_list_is_ordered_by_latest_activity(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    for contact, text in [("ana", "m1"), ("luis", "m2"), ("ana", "m3"), ("luis", "m4")]:
        add_message(link, contact, text)
    admin = client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))

    assert contacts_of(admin.get(inbox_url("whatsapp"))) == ["luis", "ana"]


def test_a_business_without_accounts_on_the_channel_gets_an_empty_list(tenant, meta_app):
    add_account(tenant, meta_app, "111", channel="whatsapp")
    rival = add_account(
        Tenant.objects.create(name="Rival Clinic"), meta_app, "333", channel="messenger"
    )
    add_message(rival, "rival-client", "Hola")
    # A message with no account at all, as in single-business mode
    Message.objects.create(
        channel="messenger",
        account=None,
        external_id="mid.single-business",
        contact_id="loose-client",
        direction=Message.DIRECTION_IN,
        message_type="text",
        text="Hola",
    )
    admin = client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))

    response = admin.get(inbox_url("messenger"))

    assert response.status_code == 200
    assert response.data["data"] == {"conversations": [], "has_more": False}


@pytest.mark.parametrize("channel", ["telegram", "WhatsApp", "all"])
def test_a_channel_other_than_whatsapp_messenger_or_instagram_is_rejected(tenant, channel):
    admin = client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))

    response = admin.get(inbox_url(channel))

    assert response.status_code == 404


def test_the_list_can_be_limited_to_one_account_and_another_business_account_is_not_found(
    tenant, meta_app
):
    first = add_account(tenant, meta_app, "111", name="Front desk")
    second = add_account(tenant, meta_app, "222", name="Night shift")
    messenger = add_account(tenant, meta_app, "444", channel="messenger")
    rival = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "333")
    add_message(first, "ana", "Hola")
    add_message(second, "luis", "Hola")
    admin = client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))

    both = admin.get(inbox_url("whatsapp"))
    only_first = admin.get(inbox_url("whatsapp"), {"account": str(first.id)})
    only_second = admin.get(inbox_url("whatsapp"), {"account": str(second.id)})

    assert sorted(contacts_of(both)) == ["ana", "luis"]
    assert contacts_of(only_first) == ["ana"]
    assert contacts_of(only_second) == ["luis"]
    for not_available in (str(rival.id), str(messenger.id)):
        response = admin.get(inbox_url("whatsapp"), {"account": not_available})
        assert response.status_code == 404
    # The same id in capitals is still my account; a malformed one is a validation error
    shouted = admin.get(inbox_url("whatsapp"), {"account": str(first.id).upper()})
    assert contacts_of(shouted) == ["ana"]
    assert admin.get(inbox_url("whatsapp"), {"account": "not-an-id"}).status_code == 400


def test_the_list_pages_with_limit_and_offset(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    for contact in ["ana", "luis", "mia"]:
        add_message(link, contact, "Hola")
    admin = client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))

    first_page = admin.get(inbox_url("whatsapp"), {"limit": 2})
    second_page = admin.get(inbox_url("whatsapp"), {"limit": 2, "offset": 2})

    assert contacts_of(first_page) == ["mia", "luis"]
    assert first_page.data["data"]["has_more"] is True
    assert contacts_of(second_page) == ["ana"]
    assert second_page.data["data"]["has_more"] is False
    for bad in ({"limit": "many"}, {"limit": 0}, {"limit": 101}, {"offset": -1}):
        assert admin.get(inbox_url("whatsapp"), bad).status_code == 400


def messages_url(channel, contact_id):
    return inbox_url(channel, contact_id, "messages")


def texts_of(response):
    return [message["text"] for message in response.data["data"]["messages"]]


def test_a_member_reads_the_messages_of_a_chat_in_chronological_order(tenant, meta_app):
    link = add_account(tenant, meta_app, "111", name="Front desk")
    add_message(link, "ana", "m1")
    add_message(link, "ana", "m2", direction=Message.DIRECTION_OUT)
    add_message(link, "ana", "m3")
    add_message(link, "luis", "other chat")
    agent = client_for(add_member(tenant, "agent@acme.test", Membership.Role.AGENT))

    response = agent.get(messages_url("whatsapp", "ana"), {"account": str(link.id)})

    assert response.status_code == 200
    data = response.data["data"]
    assert texts_of(response) == ["m1", "m2", "m3"]
    assert [message["direction"] for message in data["messages"]] == ["in", "out", "in"]
    assert data["has_more"] is False
    assert data["window_open"] is True
    assert (data["channel"], data["contact_id"]) == ("whatsapp", "ana")
    assert data["account"] == {"id": str(link.id), "name": "Front desk", "channel": "whatsapp"}
    assert agent.get(messages_url("whatsapp", "ana")).status_code == 400
    assert agent.get(messages_url("whatsapp", "ana"), {"account": "not-an-id"}).status_code == 400
    assert (
        agent.get(messages_url("whatsapp", "ana"), {"account": str(link.id).upper()}).status_code
        == 200
    )


def test_older_messages_load_with_before(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    sent = [add_message(link, "ana", f"m{number}") for number in range(1, 6)]
    admin = client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))
    url = messages_url("whatsapp", "ana")

    newest = admin.get(url, {"account": str(link.id), "limit": 2})
    older = admin.get(url, {"account": str(link.id), "limit": 2, "before": sent[3].id})
    oldest = admin.get(url, {"account": str(link.id), "limit": 2, "before": sent[1].id})

    assert texts_of(newest) == ["m4", "m5"]
    assert newest.data["data"]["has_more"] is True
    assert texts_of(older) == ["m2", "m3"]
    assert older.data["data"]["has_more"] is True
    assert texts_of(oldest) == ["m1"]
    assert oldest.data["data"]["has_more"] is False


def test_messages_of_an_account_of_another_business_answer_not_found(tenant, meta_app):
    mine = add_account(tenant, meta_app, "111", channel="whatsapp")
    mine_on_messenger = add_account(tenant, meta_app, "222", channel="messenger")
    rival = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "333")
    add_message(rival, "rival-client", "Secret of the rival")
    add_message(mine_on_messenger, "rival-client", "Wrong channel")
    admin = client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))
    url = messages_url("whatsapp", "rival-client")

    for account in (rival, mine_on_messenger):
        response = admin.get(url, {"account": str(account.id)})
        assert response.status_code == 404
        assert "Secret" not in str(response.data) and "Wrong" not in str(response.data)
    # My own account has no chat with that client: nothing to show
    assert texts_of(admin.get(url, {"account": str(mine.id)})) == []


def test_a_disconnected_account_no_longer_shows_its_chats_or_history(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    add_message(link, "ana", "Hola")
    admin = client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))
    assert contacts_of(admin.get(inbox_url("whatsapp"))) == ["ana"]

    admin.delete(f"/api/v1/channels/accounts/{link.id}/")

    assert contacts_of(admin.get(inbox_url("whatsapp"))) == []
    history = admin.get(messages_url("whatsapp", "ana"), {"account": str(link.id)})
    assert history.status_code == 404
    assert "Hola" not in str(history.data)


def test_api_docs_describe_the_inbox_without_internal_ids():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema["components"]["schemas"]
    paths = schema["paths"]

    def named(ref):
        return components[ref["$ref"].rsplit("/", 1)[1]]

    def data_of(operation):
        response = operation["responses"]["200"]["content"]["application/json"]["schema"]
        return named(named(response)["properties"]["data"])

    def query_names(operation):
        return {p["name"] for p in operation["parameters"] if p["in"] == "query"}

    listing = paths["/api/v1/inbox/{channel}/conversations/"]["get"]
    chat = named(data_of(listing)["properties"]["conversations"]["items"])
    assert "phone" not in chat["properties"]
    assert named(chat["properties"]["account"])["properties"]["id"]["format"] == "uuid"
    assert {"account", "limit", "offset"} <= query_names(listing)

    reading = paths["/api/v1/inbox/{channel}/conversations/{contact_id}/messages/"]["get"]
    message = named(data_of(reading)["properties"]["messages"]["items"])
    assert "wa_message_id" not in message["properties"]
    assert {"account", "limit", "before"} <= query_names(reading)
