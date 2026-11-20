"""
Editing the data of a contact: name, phone, email and company, for any member of its business.
"""

import uuid

import pytest
from wanps.messaging.models import App

from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message
from apps.crm.models import Contact
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


@pytest.fixture
def contact(tenant, meta_app):
    add_message(add_account(tenant, meta_app, "111"), "593990000001", "Hola", contact_name="Ana")
    return Contact.objects.get()


def file_url(contact):
    return f"/api/v1/crm/contacts/{contact.pk}/"


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_member_edits_the_data_and_the_file_shows_it(tenant, contact, role):
    any_member = client_for(add_member(tenant, "any@acme.test", role))

    response = any_member.patch(
        file_url(contact),
        {
            "name": "Ana Pérez",
            "phone": "+593 99 000 0001",
            "email": "ana@example.com",
            "company": "Pérez & Co",
        },
        format="json",
    )

    assert response.status_code == 200
    expected = {
        "name": "Ana Pérez",
        "phone": "+593 99 000 0001",
        "email": "ana@example.com",
        "company": "Pérez & Co",
    }
    assert {key: response.data["data"][key] for key in expected} == expected
    opened = any_member.get(file_url(contact)).data["data"]
    assert {key: opened[key] for key in expected} == expected


def test_fields_not_sent_stay_as_they_were(member, contact):
    member.patch(
        file_url(contact),
        {"phone": "+593 99 000 0001", "email": "ana@example.com", "company": "Pérez & Co"},
        format="json",
    )

    response = member.patch(file_url(contact), {"company": "Acme"}, format="json")

    data = response.data["data"]
    assert data["company"] == "Acme"
    assert data["phone"] == "+593 99 000 0001"
    assert data["email"] == "ana@example.com"
    assert data["name"] == "Ana"


def test_the_list_shows_the_edited_values(member, contact):
    member.patch(
        file_url(contact),
        {"name": "Ana Pérez", "phone": "0999", "email": "ana@example.com", "company": "Acme"},
        format="json",
    )

    listed = member.get("/api/v1/crm/contacts/").data["data"]["contacts"][0]

    assert listed["name"] == "Ana Pérez"
    assert listed["phone"] == "0999"
    assert listed["email"] == "ana@example.com"
    assert listed["company"] == "Acme"


def test_clearing_the_name_shows_the_channel_name_again(member, contact):
    member.patch(file_url(contact), {"name": "Ana Pérez"}, format="json")

    response = member.patch(file_url(contact), {"name": ""}, format="json")

    assert response.data["data"]["name"] == "Ana"
    assert member.get("/api/v1/crm/contacts/").data["data"]["contacts"][0]["name"] == "Ana"


def test_phone_email_and_company_can_be_cleared(member, contact):
    member.patch(
        file_url(contact),
        {"phone": "0999", "email": "ana@example.com", "company": "Acme"},
        format="json",
    )

    response = member.patch(
        file_url(contact), {"phone": "", "email": "", "company": ""}, format="json"
    )

    data = response.data["data"]
    assert (data["phone"], data["email"], data["company"]) == ("", "", "")
    assert member.get(file_url(contact)).data["data"]["company"] == ""


def test_an_invalid_email_is_rejected_and_nothing_changes(member, contact):
    response = member.patch(
        file_url(contact), {"name": "Ana Pérez", "email": "not-an-email"}, format="json"
    )

    assert response.status_code == 400
    contact.refresh_from_db()
    assert (contact.name, contact.email) == ("", "")


@pytest.mark.parametrize("phone", ["call me", "099-ABC", "(099) 123"])
def test_a_phone_with_other_characters_is_rejected_and_nothing_changes(member, contact, phone):
    response = member.patch(file_url(contact), {"phone": phone, "company": "Acme"}, format="json")

    assert response.status_code == 400
    contact.refresh_from_db()
    assert (contact.phone, contact.company) == ("", "")


def test_a_contact_of_another_business_is_not_found_and_nothing_changes(meta_app, member):
    rival = Tenant.objects.create(name="Rival Clinic")
    add_message(add_account(rival, meta_app, "222"), "593990000009", "Hola", contact_name="Zoe")
    other = Contact.objects.get()

    response = member.patch(file_url(other), {"name": "Mine now"}, format="json")

    assert response.status_code == 404
    other.refresh_from_db()
    assert other.name == ""


def test_a_contact_that_does_not_exist_is_not_found(member):
    response = member.patch(f"/api/v1/crm/contacts/{uuid.uuid4()}/", {"name": "X"}, format="json")

    assert response.status_code == 404


def test_the_file_and_the_list_tell_the_name_the_team_wrote_from_the_channel_one(member, contact):
    assert member.get(file_url(contact)).data["data"]["custom_name"] == ""

    member.patch(file_url(contact), {"name": "Ana Pérez"}, format="json")

    assert member.get(file_url(contact)).data["data"]["custom_name"] == "Ana Pérez"
    listed = member.get("/api/v1/crm/contacts/").data["data"]["contacts"][0]
    assert listed["custom_name"] == "Ana Pérez"


@pytest.mark.parametrize("phone", ["+", "---", " - "])
def test_a_phone_without_digits_is_rejected(member, contact, phone):
    response = member.patch(file_url(contact), {"phone": phone}, format="json")

    assert response.status_code == 400
    contact.refresh_from_db()
    assert contact.phone == ""


def test_the_email_is_saved_in_lowercase(member, contact):
    response = member.patch(file_url(contact), {"email": "Ana@Example.COM"}, format="json")

    assert response.data["data"]["email"] == "ana@example.com"
    assert member.get(file_url(contact)).data["data"]["email"] == "ana@example.com"
