"""
The contacts of a business: one per chat, created by themselves from the first message, listed
for any member of the business.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.test import APIClient
from wanps.messaging.models import App, Message

from apps.channels.services import disconnect
from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message, inbox_url
from apps.crm.models import Contact
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

CONTACTS_URL = "/api/v1/crm/contacts/"


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


@pytest.fixture
def member(tenant):
    return client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))


def listed_contacts(member):
    response = member.get(CONTACTS_URL)
    assert response.status_code == 200
    return response.data["data"]["contacts"]


def test_the_first_message_of_a_chat_creates_a_contact_in_the_business(tenant, meta_app, member):
    link = add_account(tenant, meta_app, "111")
    assert listed_contacts(member) == []

    add_message(link, "593990000001", "Hola", contact_name="Ana")

    assert [contact["name"] for contact in listed_contacts(member)] == ["Ana"]


def test_more_messages_of_the_same_chat_do_not_create_another_contact(tenant, meta_app, member):
    link = add_account(tenant, meta_app, "111")

    add_message(link, "593990000001", "Hola")
    add_message(link, "593990000001", "Estoy aquí")
    add_message(link, "593990000001", "Gracias", direction="out")

    assert len(listed_contacts(member)) == 1


def test_a_chat_started_by_the_business_also_creates_its_contact(tenant, meta_app, member):
    link = add_account(tenant, meta_app, "111")

    add_message(
        link, "593990000001", "Hola, le escribimos de Acme", direction="out", contact_name=""
    )

    assert len(listed_contacts(member)) == 1


def test_the_same_client_writing_to_two_accounts_makes_two_contacts(tenant, meta_app, member):
    front_desk = add_account(tenant, meta_app, "111", name="Front desk")
    sales = add_account(tenant, meta_app, "222", name="Sales")

    add_message(front_desk, "593990000001", "Hola")
    add_message(sales, "593990000001", "Hola")

    assert len(listed_contacts(member)) == 2


def test_a_failure_creating_the_contact_does_not_stop_the_message_from_being_saved(
    tenant, meta_app, member
):
    link = add_account(tenant, meta_app, "111")

    with mock.patch("apps.crm.signals.Contact.objects.get_or_create", side_effect=RuntimeError):
        add_message(link, "593990000001", "Hola")

    assert Message.objects.filter(contact_id="593990000001").count() == 1


def load_the_contacts_of_existing_chats():
    """Run the data step of the migration that gives a contact to every chat that already exists."""
    from importlib import import_module

    from django.apps import apps

    import_module("apps.crm.migrations.0002_contacts_of_existing_chats").create_contacts(apps, None)


def test_the_chats_that_existed_before_the_crm_get_their_contact(tenant, meta_app, member):
    link = add_account(tenant, meta_app, "111")
    add_message(link, "593990000001", "Hola", contact_name="Ana")
    add_message(link, "593990000002", "Buenas", contact_name="Luis")
    Contact.objects.all().delete()  # as if the chats were there before the CRM
    assert listed_contacts(member) == []

    load_the_contacts_of_existing_chats()

    assert sorted(contact["name"] for contact in listed_contacts(member)) == ["Ana", "Luis"]


def test_loading_the_existing_chats_does_not_duplicate_the_contacts_that_already_exist(
    tenant, meta_app, member
):
    link = add_account(tenant, meta_app, "111")
    add_message(link, "593990000001", "Hola", contact_name="Ana")
    add_message(link, "593990000002", "Buenas", contact_name="Luis")
    Contact.objects.filter(external_id="593990000002").delete()

    load_the_contacts_of_existing_chats()
    load_the_contacts_of_existing_chats()

    assert sorted(contact["name"] for contact in listed_contacts(member)) == ["Ana", "Luis"]


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_member_sees_the_name_channel_and_last_contact_of_the_contacts(tenant, meta_app, role):
    link = add_account(tenant, meta_app, "111")
    message = add_message(link, "593990000001", "Hola", contact_name="Ana")
    any_member = client_for(add_member(tenant, "any@acme.test", role))

    (contact,) = listed_contacts(any_member)

    assert contact["name"] == "Ana"
    assert contact["channel"] == "whatsapp"
    # The API gives dates to the second
    assert parse_datetime(contact["last_contact_at"]) == message.created_at.replace(microsecond=0)


@pytest.mark.parametrize(
    ("channel", "shown"), [("messenger", "Messenger user"), ("instagram", "Instagram user")]
)
def test_a_contact_without_a_name_shows_a_generic_one_on_messenger_and_instagram(
    tenant, meta_app, member, channel, shown
):
    link = add_account(tenant, meta_app, "111", channel=channel)
    add_message(link, "9001", "Hola", contact_name="")

    (contact,) = listed_contacts(member)

    assert contact["name"] == shown


def test_the_name_of_a_contact_is_the_one_of_the_latest_message_from_the_client(
    tenant, meta_app, member
):
    link = add_account(tenant, meta_app, "111", channel="messenger")
    add_message(link, "9001", "Hola", contact_name="")
    assert [contact["name"] for contact in listed_contacts(member)] == ["Messenger user"]

    add_message(link, "9001", "Soy yo", contact_name="Ana Pérez")
    add_message(link, "9001", "Le respondemos", direction="out", contact_name="")

    assert [contact["name"] for contact in listed_contacts(member)] == ["Ana Pérez"]


def sent(message, days_ago):
    """Put the message `days_ago` days back in time."""
    when = timezone.now() - timedelta(days=days_ago)
    Message.objects.filter(pk=message.pk).update(created_at=when)
    return when.replace(microsecond=0)


def test_the_last_contact_is_the_latest_message_of_the_chat_from_either_side(
    tenant, meta_app, member
):
    link = add_account(tenant, meta_app, "111")
    sent(add_message(link, "593990000001", "Hola"), days_ago=3)
    latest = sent(add_message(link, "593990000001", "Le escribimos", direction="out"), days_ago=1)

    (contact,) = listed_contacts(member)

    assert parse_datetime(contact["last_contact_at"]) == latest


def test_the_contacts_come_with_the_most_recent_contact_first(tenant, meta_app, member):
    link = add_account(tenant, meta_app, "111")
    sent(add_message(link, "593990000001", "Hola", contact_name="Ana"), days_ago=3)
    sent(add_message(link, "593990000002", "Buenas", contact_name="Luis"), days_ago=2)
    sent(add_message(link, "593990000001", "¿Siguen ahí?", contact_name="Ana"), days_ago=1)

    assert [contact["name"] for contact in listed_contacts(member)] == ["Ana", "Luis"]


def test_the_list_is_paginated_with_limit_and_offset(tenant, meta_app, member):
    link = add_account(tenant, meta_app, "111")
    for days_ago, name in [(1, "Ana"), (2, "Luis"), (3, "Marta")]:
        sent(add_message(link, f"5939900000{days_ago}", "Hola", contact_name=name), days_ago)

    first = member.get(CONTACTS_URL, {"limit": 2})
    second = member.get(CONTACTS_URL, {"limit": 2, "offset": 2})

    assert [c["name"] for c in first.data["data"]["contacts"]] == ["Ana", "Luis"]
    assert first.data["data"]["has_more"] is True
    assert [c["name"] for c in second.data["data"]["contacts"]] == ["Marta"]
    assert second.data["data"]["has_more"] is False


def test_a_member_never_sees_the_contacts_of_another_business(tenant, meta_app, member):
    add_message(add_account(tenant, meta_app, "111"), "593990000001", "Hola", contact_name="Ana")
    rival = Tenant.objects.create(name="Rival Clinic")
    add_message(add_account(rival, meta_app, "222"), "593990000009", "Hola", contact_name="Zoe")
    rival_member = client_for(add_member(rival, "rival@rival.test", Membership.Role.ADMIN))

    assert [c["name"] for c in listed_contacts(member)] == ["Ana"]
    assert [c["name"] for c in listed_contacts(rival_member)] == ["Zoe"]


def test_a_contact_of_a_disconnected_account_stays_in_the_list(tenant, meta_app, member):
    link = add_account(tenant, meta_app, "111")
    add_message(link, "593990000001", "Hola", contact_name="Ana")

    disconnect(link)

    assert [c["name"] for c in listed_contacts(member)] == ["Ana"]


def test_an_anonymous_visitor_cannot_list_contacts(db):
    assert APIClient().get(CONTACTS_URL).status_code == 401


def test_a_failure_finding_the_business_of_the_account_does_not_stop_the_message(
    tenant, meta_app, member
):
    link = add_account(tenant, meta_app, "111")

    with mock.patch("apps.crm.signals.ChannelAccount.all_objects.filter", side_effect=RuntimeError):
        add_message(link, "593990000001", "Hola")

    assert Message.objects.filter(contact_id="593990000001").count() == 1


def test_loading_the_existing_chats_survives_a_contact_created_meanwhile(tenant, meta_app, member):
    link = add_account(tenant, meta_app, "111")
    add_message(link, "593990000001", "Hola", contact_name="Ana")

    # The contact was created by a new message after the data step looked at the existing ones
    with mock.patch.object(Contact._base_manager, "values_list", return_value=[]):
        load_the_contacts_of_existing_chats()

    assert [contact["name"] for contact in listed_contacts(member)] == ["Ana"]


def test_a_new_message_of_a_deleted_contact_logs_no_error(tenant, meta_app, member, caplog):
    link = add_account(tenant, meta_app, "111")
    add_message(link, "593990000001", "Hola")
    Contact.objects.get().soft_delete()

    add_message(link, "593990000001", "¿Hola?")

    assert [r for r in caplog.records if r.name == "apps.crm.signals"] == []


def test_a_whatsapp_contact_without_a_name_keeps_it_empty_and_gives_its_phone(
    tenant, meta_app, member
):
    link = add_account(tenant, meta_app, "111")
    add_message(link, "593990000001", "Plantilla de bienvenida", direction="out", contact_name="")

    (contact,) = listed_contacts(member)

    # The same as the inbox: the frontend shows the phone
    assert contact["name"] == ""
    assert contact["contact_id"] == "593990000001"


def test_the_name_is_the_one_the_inbox_shows_even_when_dates_are_out_of_order(
    tenant, meta_app, member
):
    link = add_account(tenant, meta_app, "111")
    add_message(link, "593990000001", "Hola", contact_name="Ana")
    # Saved later but dated earlier (as the demo data does)
    sent(add_message(link, "593990000001", "Soy yo", contact_name="Ana Vera"), days_ago=2)
    (chat,) = member.get(inbox_url("whatsapp")).data["data"]["conversations"]

    (contact,) = listed_contacts(member)

    assert contact["name"] == chat["contact_name"] == "Ana Vera"


def test_a_message_saved_after_the_account_was_disconnected_also_creates_its_contact(
    tenant, meta_app, member
):
    link = add_account(tenant, meta_app, "111")
    disconnect(link)

    # For example a send that was queued before the disconnection
    add_message(link, "593990000001", "Le escribimos", direction="out", contact_name="")

    assert [c["contact_id"] for c in listed_contacts(member)] == ["593990000001"]
