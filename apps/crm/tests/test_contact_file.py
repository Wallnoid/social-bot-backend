"""
The file of a contact: its data and its conversations, for any member of its business.
"""

import uuid

import pytest
from django.utils.dateparse import parse_datetime
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient
from wanps.messaging.models import App, Message

from apps.channels.models import ChannelAccount
from apps.channels.services import disconnect
from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message, inbox_url
from apps.crm.models import Contact
from apps.crm.tests.test_contact_list import sent
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


@pytest.fixture
def member(tenant):
    return client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))


def file_url(contact):
    return f"/api/v1/crm/contacts/{contact.pk}/"


def opened_file(member, contact):
    response = member.get(file_url(contact))
    assert response.status_code == 200
    return response.data["data"]


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_member_opens_the_file_and_sees_the_data_of_the_contact(tenant, meta_app, role):
    link = add_account(tenant, meta_app, "111", name="Front desk")
    first = sent(add_message(link, "593990000001", "Hola", contact_name="Ana"), days_ago=3)
    last = sent(
        add_message(link, "593990000001", "Gracias", direction="out", contact_name=""), days_ago=1
    )
    any_member = client_for(add_member(tenant, "any@acme.test", role))

    data = opened_file(any_member, Contact.objects.get())

    assert data["name"] == "Ana"
    assert data["contact_id"] == "593990000001"
    assert data["channel"] == "whatsapp"
    assert data["account"] == {"id": str(link.id), "name": "Front desk", "channel": "whatsapp"}
    assert parse_datetime(data["first_contact_at"]) == first
    assert parse_datetime(data["last_contact_at"]) == last


def test_the_name_of_the_file_follows_the_rule_of_the_list(tenant, meta_app, member):
    link = add_account(tenant, meta_app, "111", channel="messenger")
    add_message(link, "9001", "Hola", contact_name="")

    assert opened_file(member, Contact.objects.get())["name"] == "Messenger user"


def test_the_file_lists_the_conversation_with_its_last_message_and_it_opens_in_the_inbox(
    tenant, meta_app, member
):
    link = add_account(tenant, meta_app, "111", name="Front desk")
    add_message(link, "593990000001", "Hola", contact_name="Ana")
    add_message(link, "593990000001", "¿En qué le ayudo?", direction="out", contact_name="")

    (conversation,) = opened_file(member, Contact.objects.get())["conversations"]

    assert conversation["connected"] is True
    assert conversation["account"] == {
        "id": str(link.id),
        "name": "Front desk",
        "channel": "whatsapp",
    }
    assert conversation["last_message"]["text"] == "¿En qué le ayudo?"
    opened = member.get(
        inbox_url(conversation["channel"], conversation["contact_id"], "messages"),
        {"account": conversation["account"]["id"]},
    )
    assert opened.status_code == 200
    assert {m["text"] for m in opened.data["data"]["messages"]} == {"Hola", "¿En qué le ayudo?"}


def test_a_chat_of_a_disconnected_account_is_marked_as_disconnected(tenant, meta_app, member):
    link = add_account(tenant, meta_app, "111", name="Front desk")
    add_message(link, "593990000001", "Hola", contact_name="Ana")
    disconnect(link)

    (conversation,) = opened_file(member, Contact.objects.get())["conversations"]

    assert conversation["connected"] is False
    assert conversation["account"]["name"] == "Front desk"


def test_a_contact_of_another_business_is_not_found(tenant, meta_app, member):
    rival = Tenant.objects.create(name="Rival Clinic")
    add_message(add_account(rival, meta_app, "222"), "593990000009", "Hola", contact_name="Zoe")

    assert member.get(file_url(Contact.objects.get())).status_code == 404


def test_a_contact_that_does_not_exist_is_not_found(member):
    assert member.get(f"/api/v1/crm/contacts/{uuid.uuid4()}/").status_code == 404


def test_an_anonymous_visitor_cannot_open_a_file(tenant, meta_app):
    add_message(add_account(tenant, meta_app, "111"), "593990000001", "Hola")

    assert APIClient().get(file_url(Contact.objects.get())).status_code == 401


def test_the_api_docs_give_the_channel_of_contacts_the_same_type_as_the_inbox(db):
    components = SchemaGenerator().get_schema(request=None, public=True)["components"]["schemas"]
    def type_of(field):
        # A read only field wraps the type: {"allOf": [{"$ref": ...}], "readOnly": true}
        return field.get("$ref") or field["allOf"][0]["$ref"]

    inbox_channel = type_of(components["InboxAccount"]["properties"]["channel"])

    for name in ["Contact", "ContactFile", "ContactConversation"]:
        assert type_of(components[name]["properties"]["channel"]) == inbox_channel, name


def test_the_whole_file_reads_only_the_chat_of_its_own_channel(tenant, meta_app, member):
    link = add_account(tenant, meta_app, "111")
    hola = sent(add_message(link, "593990000001", "Hola", contact_name="Ana"), days_ago=2)
    # A later message of the same account and client stored under another channel
    Message.objects.create(
        channel="messenger",
        account_id=link.account_id,
        external_id="mid.other-channel",
        contact_id="593990000001",
        contact_name="Otro nombre",
        direction=Message.DIRECTION_IN,
        message_type="text",
        text="Otro canal",
    )
    whatsapp = Contact.objects.get(account_id=link.account_id, external_id="593990000001")

    data = opened_file(member, whatsapp)

    assert data["name"] == "Ana"
    assert parse_datetime(data["last_contact_at"]) == hola
    assert data["conversations"][0]["last_message"]["text"] == "Hola"


def test_a_contact_whose_account_lost_its_link_to_the_business_is_not_found(
    tenant, meta_app, member
):
    link = add_account(tenant, meta_app, "111")
    add_message(link, "593990000001", "Hola", contact_name="Ana")
    contact = Contact.objects.get()
    ChannelAccount.all_objects.filter(pk=link.pk).delete()  # removed for good, not disconnected

    assert member.get(file_url(contact)).status_code == 404
