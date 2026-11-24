"""
Merging two contacts that are the same person on different channels: the one that stays has the
chats, notes and tags of both, and the other one is gone.
"""

import uuid

import pytest
from wanps.messaging.models import App

from apps.channels.models import ChannelAccount
from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message
from apps.crm.models import Contact, Note, Stage, Tag
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
def ana(whatsapp):
    """Ana on WhatsApp: the contact that stays."""
    add_message(whatsapp, "593990000001", "Hola", contact_name="Ana")
    return Contact.objects.get(external_id="593990000001")


@pytest.fixture
def ana_on_messenger(messenger):
    """The same person on Messenger: the contact that goes."""
    add_message(messenger, "psid-1", "Hola", contact_name="Ana Paz")
    return Contact.objects.get(external_id="psid-1")


@pytest.fixture
def member(tenant):
    return client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))


def merge(member, kept, absorbed_id):
    return member.post(
        f"{CONTACTS_URL}{kept.pk}/merge/", {"contact": str(absorbed_id)}, format="json"
    )


def file_of(member, contact):
    response = member.get(f"{CONTACTS_URL}{contact.pk}/")
    assert response.status_code == 200
    return response.data["data"]


def chats_of(member, contact):
    return {
        (chat["channel"], chat["contact_id"]) for chat in file_of(member, contact)["conversations"]
    }


def listed_ids(member):
    return [c["id"] for c in member.get(CONTACTS_URL).data["data"]["contacts"]]


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_member_merges_two_contacts_and_the_one_that_stays_has_both_chats(
    tenant, ana, ana_on_messenger, role
):
    any_member = client_for(add_member(tenant, "any@acme.test", role))

    response = merge(any_member, ana, ana_on_messenger.pk)

    assert response.status_code == 200
    expected = {("whatsapp", "593990000001"), ("messenger", "psid-1")}
    assert {
        (chat["channel"], chat["contact_id"]) for chat in response.data["data"]["conversations"]
    } == expected
    assert chats_of(any_member, ana) == expected
    assert listed_ids(any_member) == [str(ana.pk)]
    assert any_member.get(f"{CONTACTS_URL}{ana_on_messenger.pk}/").status_code == 404


def test_the_notes_and_tags_of_both_contacts_stay_with_the_one_that_stays(
    tenant, ana, ana_on_messenger, member
):
    Note.objects.create(contact=ana, text="Prefiere las tardes")
    Note.objects.create(contact=ana_on_messenger, text="Escribió por Messenger")
    vip, wholesale = (
        Tag.objects.create(tenant=tenant, name="VIP"),
        Tag.objects.create(tenant=tenant, name="Mayorista"),
    )
    ana.tags.add(vip)
    ana_on_messenger.tags.add(vip, wholesale)

    merge(member, ana, ana_on_messenger.pk)

    notes = member.get(f"{CONTACTS_URL}{ana.pk}/notes/").data["data"]["notes"]
    assert {note["text"] for note in notes} == {"Prefiere las tardes", "Escribió por Messenger"}
    assert sorted(tag["name"] for tag in file_of(member, ana)["tags"]) == ["Mayorista", "VIP"]


def test_the_contact_that_stays_keeps_its_data_and_fills_what_it_had_empty(
    tenant, ana, ana_on_messenger, member
):
    interested = Stage.objects.get(tenant=tenant, name="Interesado")
    carla = add_member(tenant, "carla@acme.test", Membership.Role.AGENT, first_name="Carla")
    Contact.objects.filter(pk=ana.pk).update(
        name="", phone="111", email="", company="Acme", stage=interested
    )
    Contact.objects.filter(pk=ana_on_messenger.pk).update(
        name="Ana Paz", phone="999", email="ana@example.test", company="Other", assigned_to=carla
    )

    merge(member, ana, ana_on_messenger.pk)

    data = file_of(member, ana)
    assert data["custom_name"] == "Ana Paz"
    assert data["phone"] == "111"
    assert data["email"] == "ana@example.test"
    assert data["company"] == "Acme"
    assert data["stage"]["name"] == "Interesado"
    assert data["assigned_to"]["id"] == str(carla.pk)


def test_the_person_in_charge_of_the_contact_that_stays_is_kept(
    tenant, ana, ana_on_messenger, member
):
    luis = add_member(tenant, "luis@acme.test", Membership.Role.AGENT)
    carla = add_member(tenant, "carla@acme.test", Membership.Role.AGENT)
    Contact.objects.filter(pk=ana.pk).update(assigned_to=luis)
    Contact.objects.filter(pk=ana_on_messenger.pk).update(assigned_to=carla)

    merge(member, ana, ana_on_messenger.pk)

    assert file_of(member, ana)["assigned_to"]["id"] == str(luis.pk)


def test_a_message_of_a_merged_chat_goes_to_the_contact_that_stays(
    ana, ana_on_messenger, messenger, member
):
    merge(member, ana, ana_on_messenger.pk)

    add_message(messenger, "psid-1", "Sigo aquí", contact_name="Ana Paz")

    assert Contact.all_objects.count() == 2
    assert listed_ids(member) == [str(ana.pk)]
    assert chats_of(member, ana) == {("whatsapp", "593990000001"), ("messenger", "psid-1")}


def test_the_chat_of_a_merged_contact_brings_the_contact_that_stays_in_the_inbox(
    ana, ana_on_messenger, messenger, member
):
    merge(member, ana, ana_on_messenger.pk)

    response = member.get(
        f"/api/v1/inbox/messenger/conversations/psid-1/messages/?account={messenger.pk}"
    )

    assert response.status_code == 200
    assert response.data["data"]["contact"]["id"] == str(ana.pk)


def test_merging_again_keeps_every_chat_in_the_last_contact(
    tenant, meta_app, ana, ana_on_messenger, member
):
    instagram = add_account(tenant, meta_app, "333", channel="instagram")
    add_message(instagram, "igsid-1", "Hola", contact_name="Ana IG")
    third = Contact.objects.get(external_id="igsid-1")
    merge(member, ana, ana_on_messenger.pk)

    merge(member, third, ana.pk)

    assert chats_of(member, third) == {
        ("whatsapp", "593990000001"),
        ("messenger", "psid-1"),
        ("instagram", "igsid-1"),
    }
    assert listed_ids(member) == [str(third.pk)]


def test_the_list_and_the_stage_counts_count_a_merged_contact_once(ana, ana_on_messenger, member):
    merge(member, ana, ana_on_messenger.pk)

    stages = member.get("/api/v1/crm/stages/").data["data"]["stages"]

    assert {stage["name"]: stage["contacts"] for stage in stages}["Nuevo"] == 1
    assert len(member.get(CONTACTS_URL).data["data"]["contacts"]) == 1


def test_a_contact_of_another_business_one_that_does_not_exist_or_the_same_one_is_rejected(
    tenant, meta_app, ana, ana_on_messenger, member
):
    rival = Tenant.objects.create(name="Rival Clinic")
    add_message(add_account(rival, meta_app, "999"), "593990000009", "Hola", contact_name="Zoe")
    theirs = Contact.objects.get(tenant=rival)

    for other in (theirs.pk, uuid.uuid4(), ana.pk):
        response = merge(member, ana, other)

        assert response.status_code == 400
        assert "contact" in response.data["errors"]
    assert chats_of(member, ana) == {("whatsapp", "593990000001")}
    assert set(listed_ids(member)) == {str(ana.pk), str(ana_on_messenger.pk)}
    assert Contact.objects.filter(tenant=rival).count() == 1


def test_a_contact_that_was_already_merged_cannot_be_merged_again_and_the_kept_one_must_exist(
    tenant, ana, ana_on_messenger, member
):
    merge(member, ana, ana_on_messenger.pk)

    again = merge(member, ana, ana_on_messenger.pk)
    missing = merge(member, Contact(pk=uuid.uuid4()), ana.pk)

    assert again.status_code == 400
    assert missing.status_code == 404


def test_the_merge_url_only_merges(ana, ana_on_messenger, member):
    url = f"{CONTACTS_URL}{ana.pk}/merge/"

    assert member.get(url).status_code == 405
    assert member.patch(url, {"custom_name": "Otro"}, format="json").status_code == 405
    assert file_of(member, ana)["custom_name"] == ""


def test_a_contact_that_cannot_give_its_file_is_refused_before_anything_is_merged(
    ana, ana_on_messenger, member
):
    ChannelAccount.all_objects.filter(account=ana.account).delete()

    response = merge(member, ana, ana_on_messenger.pk)

    assert response.status_code == 404
    assert Contact.objects.filter(pk=ana_on_messenger.pk).exists()


def test_a_person_in_charge_who_left_the_business_is_not_passed_on(
    tenant, ana, ana_on_messenger, member
):
    carla = add_member(tenant, "carla@acme.test", Membership.Role.AGENT)
    Contact.objects.filter(pk=ana_on_messenger.pk).update(assigned_to=carla)
    carla.soft_delete()

    merge(member, ana, ana_on_messenger.pk)

    assert file_of(member, ana)["assigned_to"] is None
    assert Contact.objects.get(pk=ana.pk).assigned_to_id is None


def test_a_restored_contact_gets_its_own_chat_back_in_the_inbox(
    ana, ana_on_messenger, messenger, member
):
    merge(member, ana, ana_on_messenger.pk)
    Contact.all_objects.get(pk=ana_on_messenger.pk).restore()

    response = member.get(
        f"/api/v1/inbox/messenger/conversations/psid-1/messages/?account={messenger.pk}"
    )

    assert response.data["data"]["contact"]["id"] == str(ana_on_messenger.pk)
