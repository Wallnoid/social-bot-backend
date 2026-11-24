"""
The list and the search of the contacts count every chat of a merged contact: its own and the
ones of the contacts merged into it.
"""

import pytest
from django.utils.dateparse import parse_datetime
from wanps.messaging.models import App

from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message
from apps.crm.models import Contact, Stage
from apps.crm.tests.test_contact_list import sent
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
def whatsapp(tenant, meta_app):
    return add_account(tenant, meta_app, "111")


@pytest.fixture
def messenger(tenant, meta_app):
    return add_account(tenant, meta_app, "222", channel="messenger")


@pytest.fixture
def member(tenant):
    return client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))


def contact_of(link, client, name):
    add_message(link, client, "Hola", contact_name=name)
    return Contact.objects.get(account=link.account, external_id=client)


def merge(member, kept, absorbed):
    response = member.post(
        f"{CONTACTS_URL}{kept.pk}/merge/", {"contact": str(absorbed.pk)}, format="json"
    )
    assert response.status_code == 200


def listed(member, **query):
    response = member.get(CONTACTS_URL, query)
    assert response.status_code == 200
    return response.data["data"]["contacts"]


def found(member, **query):
    return [contact["id"] for contact in listed(member, **query)]


def test_a_message_in_a_merged_chat_moves_the_contact_up_and_sets_its_last_contact(
    whatsapp, messenger, member
):
    sent(add_message(whatsapp, "593990000001", "Hola", contact_name="Ana"), days_ago=5)
    sent(add_message(whatsapp, "593990000002", "Hola", contact_name="Luis"), days_ago=2)
    sent(add_message(messenger, "psid-1", "Hola", contact_name="Ana Paz"), days_ago=9)
    ana = Contact.objects.get(external_id="593990000001")
    luis = Contact.objects.get(external_id="593990000002")
    merge(member, ana, Contact.objects.get(external_id="psid-1"))
    assert found(member) == [str(luis.pk), str(ana.pk)]

    latest = sent(add_message(messenger, "psid-1", "Sigo aquí", contact_name="Ana Paz"), days_ago=0)

    contacts = listed(member)
    assert [contact["id"] for contact in contacts] == [str(ana.pk), str(luis.pk)]
    assert parse_datetime(contacts[0]["last_contact_at"]) == latest


def test_searching_the_channel_name_of_a_merged_chat_finds_the_contact_once(
    whatsapp, messenger, member
):
    ana = contact_of(whatsapp, "593990000001", "Ana Paz")
    ana_on_messenger = contact_of(messenger, "psid-1", "Ana Paz Messenger")
    merge(member, ana, ana_on_messenger)

    assert found(member, search="messenger") == [str(ana.pk)]
    assert found(member, search="ana paz") == [str(ana.pk)]


def test_searching_the_number_or_the_name_and_phone_the_team_wrote_on_a_merged_contact_finds_it(
    whatsapp, messenger, member
):
    ana = contact_of(messenger, "psid-1", "Ana")
    ana_on_whatsapp = contact_of(whatsapp, "593990000001", "Ana")
    Contact.objects.filter(pk=ana.pk).update(name="Ana Paz", phone="111")
    Contact.objects.filter(pk=ana_on_whatsapp.pk).update(name="Doctora Gil", phone="+593 98 765")
    ana.refresh_from_db()
    ana_on_whatsapp.refresh_from_db()
    merge(member, ana, ana_on_whatsapp)

    assert found(member, search="0000001") == [str(ana.pk)]
    assert found(member, search="doctora") == [str(ana.pk)]
    assert found(member, search="98 765") == [str(ana.pk)]
    assert found(member, search="zzz") == []


def test_the_other_filters_still_apply_to_the_search_of_a_merged_chat(
    tenant, whatsapp, messenger, member
):
    ana = contact_of(whatsapp, "593990000001", "Ana")
    ana_on_messenger = contact_of(messenger, "psid-1", "Ana Messenger")
    merge(member, ana, ana_on_messenger)
    interested = Stage.objects.get(tenant=tenant, name="Interesado")
    client = Stage.objects.get(tenant=tenant, name="Nuevo")

    assert found(member, search="messenger", stage=str(client.pk)) == [str(ana.pk)]
    assert found(member, search="messenger", stage=str(interested.pk)) == []


def test_a_contact_without_merges_does_not_change_and_a_merged_one_does_not_bring_others(
    whatsapp, messenger, member
):
    ana = contact_of(whatsapp, "593990000001", "Ana")
    ana_on_messenger = contact_of(messenger, "psid-1", "Ana Paz Messenger")
    luis = contact_of(whatsapp, "593990000002", "Luis")
    merge(member, ana, ana_on_messenger)

    assert found(member, search="luis") == [str(luis.pk)]
    assert found(member, search="messenger") == [str(ana.pk)]
    assert sorted(found(member)) == sorted([str(ana.pk), str(luis.pk)])
