"""
The person in charge of a contact: a member of the business that takes care of the client.
"""

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
def contact(tenant, meta_app):
    add_message(add_account(tenant, meta_app, "111"), "593990000001", "Hola", contact_name="Ana")
    return Contact.objects.get()


@pytest.fixture
def ana(tenant):
    return add_member(
        tenant, "ana@acme.test", Membership.Role.AGENT, first_name="Ana", last_name="Paz"
    )


def file_url(contact):
    return f"/api/v1/crm/contacts/{contact.pk}/"


def in_charge_in_file(member, contact):
    return member.get(file_url(contact)).data["data"]["assigned_to"]


def in_charge_in_list(member):
    return member.get("/api/v1/crm/contacts/").data["data"]["contacts"][0]["assigned_to"]


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_member_assigns_a_contact_to_a_member_and_the_list_and_the_file_show_who_is_in_charge(
    tenant, contact, ana, role
):
    member = client_for(add_member(tenant, "member@acme.test", role))
    assert in_charge_in_file(member, contact) is None

    response = member.patch(file_url(contact), {"assigned_to": str(ana.pk)}, format="json")

    assert response.status_code == 200
    expected = {"id": str(ana.pk), "name": "Ana Paz"}
    assert response.data["data"]["assigned_to"] == expected
    assert in_charge_in_file(member, contact) == expected
    assert in_charge_in_list(member) == expected


def test_assigning_another_member_or_taking_the_person_off_changes_it_for_everyone(
    tenant, contact, ana
):
    luis = add_member(
        tenant, "luis@acme.test", Membership.Role.SUPERVISOR, first_name="Luis", last_name="Gil"
    )
    agent = client_for(add_member(tenant, "agent@acme.test", Membership.Role.AGENT))
    other = client_for(add_member(tenant, "other@acme.test", Membership.Role.ADMIN))
    agent.patch(file_url(contact), {"assigned_to": str(ana.pk)}, format="json")

    agent.patch(file_url(contact), {"assigned_to": str(luis.pk)}, format="json")

    assert in_charge_in_file(other, contact) == {"id": str(luis.pk), "name": "Luis Gil"}
    assert in_charge_in_list(other) == {"id": str(luis.pk), "name": "Luis Gil"}

    response = agent.patch(file_url(contact), {"assigned_to": None}, format="json")

    assert response.status_code == 200
    assert in_charge_in_file(other, contact) is None
    assert in_charge_in_list(other) is None


@pytest.mark.parametrize("kind", ["member of another business", "does not exist", "not an id"])
def test_a_person_who_is_not_a_member_of_the_business_is_rejected_and_the_contact_does_not_change(
    tenant, contact, ana, kind
):
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))
    member.patch(file_url(contact), {"assigned_to": str(ana.pk)}, format="json")
    rival = Tenant.objects.create(name="Rival Clinic")
    stranger = add_member(rival, "boss@rival.test", Membership.Role.ADMIN)
    wrong = {
        "member of another business": str(stranger.pk),
        "does not exist": "6b0f3c38-0000-4000-8000-000000000000",
        "not an id": "ana",
    }[kind]

    response = member.patch(
        file_url(contact), {"assigned_to": wrong, "company": "Changed SA"}, format="json"
    )

    assert response.status_code == 400
    assert in_charge_in_file(member, contact) == {"id": str(ana.pk), "name": "Ana Paz"}
    assert member.get(file_url(contact)).data["data"]["company"] == ""


def test_when_the_person_in_charge_leaves_the_business_the_contact_shows_nobody_in_charge(
    tenant, contact, ana
):
    admin = client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))
    admin.patch(file_url(contact), {"assigned_to": str(ana.pk)}, format="json")

    removed = admin.delete(f"/api/v1/tenants/members/{ana.pk}/")

    assert removed.status_code == 200
    assert in_charge_in_file(admin, contact) is None
    assert in_charge_in_list(admin) is None
