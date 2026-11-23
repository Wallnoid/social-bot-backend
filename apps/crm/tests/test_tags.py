"""
The tags of the contacts: any member tags a contact by typing a name, and the business keeps one
tag per name.
"""

from unittest import mock

import pytest
from wanps.messaging.models import App

from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message
from apps.crm import views
from apps.crm.models import Contact, Tag
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


@pytest.fixture
def contact(tenant, meta_app):
    add_message(add_account(tenant, meta_app, "111"), "593990000001", "Hola", contact_name="Ana")
    return Contact.objects.get()


@pytest.fixture
def member(tenant):
    return client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))


def tags_url(contact):
    return f"/api/v1/crm/contacts/{contact.pk}/tags/"


def file_tags(member, contact):
    response = member.get(f"/api/v1/crm/contacts/{contact.pk}/")
    assert response.status_code == 200
    return [tag["name"] for tag in response.data["data"]["tags"]]


def listed_tags(member):
    response = member.get("/api/v1/crm/contacts/")
    assert response.status_code == 200
    return [
        [tag["name"] for tag in contact["tags"]] for contact in response.data["data"]["contacts"]
    ]


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_member_tags_a_contact_by_its_name_and_sees_the_tag_in_the_list_and_the_file(
    tenant, contact, role
):
    member = client_for(add_member(tenant, "member@acme.test", role))

    response = member.post(tags_url(contact), {"name": "VIP"}, format="json")

    assert response.status_code == 201
    assert response.data["data"]["name"] == "VIP"
    assert file_tags(member, contact) == ["VIP"]
    assert listed_tags(member) == [["VIP"]]


def test_the_same_name_with_other_capitalization_uses_the_same_tag(
    tenant, meta_app, member, contact
):
    add_message(add_account(tenant, meta_app, "222"), "593990000002", "Buenas", contact_name="Luis")
    other = Contact.objects.exclude(pk=contact.pk).get()

    first = member.post(tags_url(contact), {"name": "Mayorista"}, format="json")
    second = member.post(tags_url(other), {"name": "MAYORISTA"}, format="json")

    assert second.data["data"]["id"] == first.data["data"]["id"]
    assert second.data["data"]["name"] == "Mayorista"
    assert Tag.objects.filter(tenant=tenant).count() == 1
    assert file_tags(member, other) == ["Mayorista"]


def test_adding_a_tag_the_contact_already_has_does_not_duplicate_it(member, contact):
    first = member.post(tags_url(contact), {"name": "VIP"}, format="json")

    again = member.post(tags_url(contact), {"name": "vip"}, format="json")

    assert first.status_code == 201
    assert again.status_code == 200
    assert again.data["data"]["id"] == first.data["data"]["id"]
    assert file_tags(member, contact) == ["VIP"]


@pytest.mark.parametrize("name", ["", "   ", "\n\t", "a" * 51])
def test_an_empty_blank_or_too_long_name_is_rejected_and_nothing_is_saved(
    tenant, member, contact, name
):
    response = member.post(tags_url(contact), {"name": name}, format="json")

    assert response.status_code == 400
    assert file_tags(member, contact) == []
    assert Tag.objects.filter(tenant=tenant).count() == 0


def test_a_name_of_exactly_50_characters_is_saved(member, contact):
    response = member.post(tags_url(contact), {"name": "a" * 50}, format="json")

    assert response.status_code == 201
    assert file_tags(member, contact) == ["a" * 50]


def test_removing_a_tag_takes_it_off_the_contact_and_the_other_contacts_keep_theirs(
    tenant, meta_app, member, contact
):
    add_message(add_account(tenant, meta_app, "222"), "593990000002", "Buenas", contact_name="Luis")
    other = Contact.objects.exclude(pk=contact.pk).get()
    vip = member.post(tags_url(contact), {"name": "VIP"}, format="json").data["data"]["id"]
    member.post(tags_url(contact), {"name": "Mayorista"}, format="json")
    member.post(tags_url(other), {"name": "VIP"}, format="json")

    response = member.delete(f"{tags_url(contact)}{vip}/")

    assert response.status_code == 200
    assert file_tags(member, contact) == ["Mayorista"]
    assert file_tags(member, other) == ["VIP"]


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_member_lists_the_tags_of_the_business_with_their_contacts_and_never_the_ones_of_another(
    tenant, meta_app, member, contact, role
):
    add_message(add_account(tenant, meta_app, "222"), "593990000002", "Buenas", contact_name="Luis")
    other = Contact.objects.exclude(pk=contact.pk).get()
    member.post(tags_url(contact), {"name": "VIP"}, format="json")
    member.post(tags_url(other), {"name": "VIP"}, format="json")
    member.post(tags_url(other), {"name": "Mayorista"}, format="json")
    rival = Tenant.objects.create(name="Rival Clinic")
    rival.tags.create(name="Secreto del rival")
    reader = client_for(add_member(tenant, "reader@acme.test", role))

    response = reader.get("/api/v1/crm/tags/")

    assert response.status_code == 200
    assert [(tag["name"], tag["contacts"]) for tag in response.data["data"]["tags"]] == [
        ("Mayorista", 1),
        ("VIP", 2),
    ]


def test_a_contact_or_a_tag_of_another_business_or_a_deleted_contact_is_not_found_and_nothing_changes(
    tenant, meta_app, member, contact
):
    rival = Tenant.objects.create(name="Rival Clinic")
    add_message(add_account(rival, meta_app, "222"), "593990000009", "Hola", contact_name="Zoe")
    theirs = Contact.objects.get(tenant=rival)
    their_tag = rival.tags.create(name="Secreto del rival")
    theirs.tags.add(their_tag)
    mine = member.post(tags_url(contact), {"name": "VIP"}, format="json").data["data"]["id"]

    assert member.post(tags_url(theirs), {"name": "Mine now"}, format="json").status_code == 404
    assert member.delete(f"{tags_url(theirs)}{their_tag.pk}/").status_code == 404
    assert member.delete(f"{tags_url(contact)}{their_tag.pk}/").status_code == 404
    contact.delete()
    assert member.post(tags_url(contact), {"name": "Late"}, format="json").status_code == 404
    assert member.delete(f"{tags_url(contact)}{mine}/").status_code == 404
    assert [tag.name for tag in theirs.tags.all()] == ["Secreto del rival"]
    assert not Tag.objects.filter(tenant=tenant, name__in=["Mine now", "Late"]).exists()
    assert list(Contact.all_objects.get(pk=contact.pk).tags.values_list("name", flat=True)) == [
        "VIP"
    ]


def test_a_tag_created_by_another_request_meanwhile_is_reused_instead_of_failing(
    tenant, member, contact
):
    existing = Tag.objects.create(tenant=tenant, name="VIP")
    real_lookup = views.find_tag
    lookups = []

    def first_lookup_misses(tenant, name):
        # The other request had not saved the tag yet when this one looked for it
        lookups.append(name)
        return None if len(lookups) == 1 else real_lookup(tenant, name)

    with mock.patch.object(views, "find_tag", side_effect=first_lookup_misses):
        response = member.post(tags_url(contact), {"name": "vip"}, format="json")

    assert response.status_code == 201
    assert response.data["data"]["id"] == str(existing.pk)
    assert Tag.objects.filter(tenant=tenant).count() == 1
    assert file_tags(member, contact) == ["VIP"]
