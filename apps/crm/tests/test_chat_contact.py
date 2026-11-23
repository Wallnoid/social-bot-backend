"""
The contact of a chat of the inbox: the chat brings it with its stage, so a member opens its file
and moves its stage without leaving the conversation.
"""

import pytest
from wanps.messaging.models import App

from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message
from apps.crm.models import Contact
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

CLIENT = "593990000001"


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


def chat_url(link, client=CLIENT):
    return f"/api/v1/inbox/whatsapp/conversations/{client}/messages/?account={link.pk}"


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_member_opening_a_chat_gets_its_contact_with_its_current_stage(tenant, meta_app, role):
    link = add_account(tenant, meta_app, "111")
    add_message(link, CLIENT, "Hola", contact_name="Ana")
    contact = Contact.objects.get()
    member = client_for(add_member(tenant, "member@acme.test", role))

    response = member.get(chat_url(link))

    assert response.status_code == 200
    assert response.data["data"]["contact"] == {
        "id": str(contact.pk),
        "stage": {"id": str(contact.stage_id), "name": "Nuevo"},
    }


def test_a_chat_whose_contact_does_not_exist_gets_none(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    add_message(link, CLIENT, "Hola", contact_name="Ana")
    Contact.objects.get().delete()
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    response = member.get(chat_url(link))

    assert response.status_code == 200
    assert response.data["data"]["contact"] is None


def test_a_chat_brings_its_own_contact_and_not_the_one_of_another_business_with_the_same_client(
    tenant, meta_app
):
    link = add_account(tenant, meta_app, "111")
    add_message(link, CLIENT, "Hola", contact_name="Ana")
    mine = Contact.objects.get()
    rival_link = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "222")
    add_message(rival_link, CLIENT, "Hola", contact_name="Ana")
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    response = member.get(chat_url(link))

    assert Contact.objects.count() == 2
    assert response.data["data"]["contact"]["id"] == str(mine.pk)


def test_moving_the_contact_from_the_chat_shows_the_new_stage_in_the_chat_the_pipeline_the_list_and_the_file(
    tenant, meta_app
):
    link = add_account(tenant, meta_app, "111")
    add_message(link, CLIENT, "Hola", contact_name="Ana")
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))
    chat = member.get(chat_url(link)).data["data"]["contact"]
    interesado = tenant.stages.get(name="Interesado")

    moved = member.patch(
        f"/api/v1/crm/contacts/{chat['id']}/", {"stage": str(interesado.pk)}, format="json"
    )

    assert moved.status_code == 200
    expected = {"id": str(interesado.pk), "name": "Interesado"}
    assert member.get(chat_url(link)).data["data"]["contact"]["stage"] == expected
    stages = member.get("/api/v1/crm/stages/").data["data"]["stages"]
    assert {stage["name"]: stage["contacts"] for stage in stages}["Interesado"] == 1
    assert member.get("/api/v1/crm/contacts/").data["data"]["contacts"][0]["stage"] == expected
    assert member.get(f"/api/v1/crm/contacts/{chat['id']}/").data["data"]["stage"] == expected
