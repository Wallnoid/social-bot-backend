"""
The name of a client in the chat list: while Meta has not given it, Messenger and Instagram show
a generic name instead of an empty one. The generic name is shown, never saved.
"""

import pytest
from wanps.messaging.models import App, Message

from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message, inbox_url
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


def listed_name(member, channel):
    response = member.get(inbox_url(channel))
    assert response.status_code == 200
    (chat,) = response.data["data"]["conversations"]
    return chat["contact_name"]


@pytest.mark.parametrize(
    ("channel", "shown"), [("messenger", "Messenger user"), ("instagram", "Instagram user")]
)
def test_a_chat_without_a_name_shows_a_generic_one_on_messenger_and_instagram(
    tenant, meta_app, member, channel, shown
):
    link = add_account(tenant, meta_app, "111", channel=channel)
    add_message(link, "9001", "Hola", contact_name="")

    assert listed_name(member, channel) == shown


@pytest.mark.parametrize("channel", ["messenger", "instagram"])
def test_a_chat_with_a_name_shows_that_name(tenant, meta_app, member, channel):
    link = add_account(tenant, meta_app, "111", channel=channel)
    add_message(link, "9001", "Hola", contact_name="Ana Vera")

    assert listed_name(member, channel) == "Ana Vera"


def test_the_generic_name_is_replaced_once_the_name_arrives(tenant, meta_app, member):
    link = add_account(tenant, meta_app, "111", channel="messenger")
    add_message(link, "9001", "Hola", contact_name="")
    assert listed_name(member, "messenger") == "Messenger user"

    add_message(link, "9001", "Seguimos", contact_name="Ana Vera")

    assert listed_name(member, "messenger") == "Ana Vera"


def test_whatsapp_keeps_an_empty_name_empty(tenant, meta_app, member):
    link = add_account(tenant, meta_app, "111", channel="whatsapp")
    add_message(link, "593990000001", "Hola", contact_name="")

    assert listed_name(member, "whatsapp") == ""


def test_the_generic_name_is_never_saved(tenant, meta_app, member):
    link = add_account(tenant, meta_app, "111", channel="messenger")
    add_message(link, "9001", "Hola", contact_name="")

    listed_name(member, "messenger")

    assert Message.objects.get(contact_id="9001").contact_name == ""
