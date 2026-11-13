"""
What the team sees of a client blocked by the bot, and lifting the block: the inbox shows until when,
and a supervisor or an admin can lift it (in case it was a mistake).
"""

import json
from datetime import timedelta

import pytest
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from wanps.messaging.models import App

from apps.channels.models import ClientStrikes
from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message, inbox_url, messages_url
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

CLIENT = "593990000001"
OTHER = "593990000002"


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


@pytest.fixture
def link(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    add_message(link, CLIENT, "Hi, are you open?")
    add_message(link, OTHER, "Hello")
    return link


def member_with(tenant, role):
    return client_for(add_member(tenant, f"{role}@acme.test", role))


def block(link, contact=CLIENT, minutes=30):
    return ClientStrikes.objects.create(
        account=link.account,
        contact_id=contact,
        strikes=0,
        blocked_until=timezone.now() + timedelta(minutes=minutes),
    )


def unblock_url(channel="whatsapp", contact=CLIENT):
    return inbox_url(channel, contact, "unblock")


def lift(api, link, contact=CLIENT, channel="whatsapp"):
    return api.post(unblock_url(channel, contact), {"account": str(link.id)}, format="json")


def listed(api):
    chats = api.get(inbox_url("whatsapp")).data["data"]["conversations"]
    return {chat["contact_id"]: chat for chat in chats}


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_member_sees_until_when_a_client_is_blocked_in_the_list_and_none_for_the_others(
    tenant, link, role
):
    blocked = block(link)
    api = member_with(tenant, role)

    chats = listed(api)

    assert chats[CLIENT]["bot_blocked_until"] is not None
    assert chats[OTHER]["bot_blocked_until"] is None
    shown = chats[CLIENT]["bot_blocked_until"]
    assert abs(timezone.datetime.fromisoformat(shown) - blocked.blocked_until) < timedelta(
        seconds=1
    )


def test_the_chat_shows_it_too(tenant, link):
    block(link)
    api = member_with(tenant, Membership.Role.AGENT)

    chat = api.get(messages_url("whatsapp", CLIENT), {"account": str(link.id)})

    assert chat.data["data"]["bot_blocked_until"] is not None
    other = api.get(messages_url("whatsapp", OTHER), {"account": str(link.id)})
    assert other.data["data"]["bot_blocked_until"] is None


def test_a_block_that_already_ended_shows_nothing(tenant, link):
    block(link, minutes=-5)
    api = member_with(tenant, Membership.Role.AGENT)

    assert listed(api)[CLIENT]["bot_blocked_until"] is None


def test_the_block_of_a_client_in_another_account_is_not_shown_here(tenant, meta_app, link):
    rival = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "222")
    block(rival)
    api = member_with(tenant, Membership.Role.AGENT)

    assert listed(api)[CLIENT]["bot_blocked_until"] is None


@pytest.mark.parametrize("role", [Membership.Role.SUPERVISOR, Membership.Role.ADMIN])
def test_a_supervisor_or_an_admin_lifts_the_block_and_the_faults(tenant, link, role):
    row = block(link)
    ClientStrikes.objects.filter(pk=row.pk).update(strikes=3)
    api = member_with(tenant, role)

    response = lift(api, link)

    assert response.status_code == 200
    row.refresh_from_db()
    assert (row.blocked_until, row.strikes) == (None, 0)
    assert listed(api)[CLIENT]["bot_blocked_until"] is None


def test_an_agent_cannot_lift_the_block(tenant, link):
    row = block(link)
    api = member_with(tenant, Membership.Role.AGENT)

    response = lift(api, link)

    assert response.status_code == 403
    row.refresh_from_db()
    assert row.blocked_until is not None


def test_an_account_of_another_business_or_a_chat_that_does_not_exist_is_not_found(
    tenant, meta_app, link
):
    rival = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "222")
    add_message(rival, CLIENT, "Hi")
    rival_row = block(rival)
    api = member_with(tenant, Membership.Role.ADMIN)

    assert lift(api, rival).status_code == 404
    assert lift(api, link, contact="999000999").status_code == 404
    rival_row.refresh_from_db()
    assert rival_row.blocked_until is not None


def test_lifting_a_block_that_does_not_exist_is_fine(tenant, link):
    api = member_with(tenant, Membership.Role.ADMIN)

    response = lift(api, link)

    assert response.status_code == 200
    assert not ClientStrikes.objects.exists()


def test_the_api_docs_describe_the_block_field_and_the_endpoint():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema["components"]["schemas"]

    for name in ("Conversation", "ChatMessages"):
        field = components[name]["properties"]["bot_blocked_until"]
        assert field.get("nullable") is True or "null" in json.dumps(field)
    path = schema["paths"]["/api/v1/inbox/{channel}/conversations/{contact_id}/unblock/"]
    assert "post" in path
