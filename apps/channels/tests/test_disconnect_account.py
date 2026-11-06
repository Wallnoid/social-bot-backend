"""
Tests for disconnecting a business's channel account.
"""

import copy

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from drf_spectacular.generators import SchemaGenerator
from wanps.messaging.models import Account, App, Message

from apps.channels.models import ChannelAccount, SharedMetaApp
from apps.channels.tests.test_connect_account import connect, post_signed, whatsapp_message_for
from apps.channels.tests.test_manage_accounts import (
    ACCOUNTS_URL,
    TOKEN,
    add_account,
    detail_url,
)
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def admin_client(tenant):
    return client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


def test_admin_disconnects_an_account_and_it_leaves_the_list(admin_client, tenant, meta_app):
    gone = add_account(tenant, meta_app, "111", name="Old number")
    kept = add_account(tenant, meta_app, "222", name="Front desk")

    response = admin_client.delete(detail_url(gone))

    assert response.status_code == 200
    listed = admin_client.get(ACCOUNTS_URL).data["data"]
    assert [account["id"] for account in listed] == [str(kept.id)]
    assert ChannelAccount.all_objects.get(pk=gone.pk).is_deleted


def test_a_disconnected_account_is_turned_off_and_its_token_erased_but_keeps_its_history(
    admin_client, tenant, meta_app
):
    link = add_account(tenant, meta_app, "111")
    Account.objects.filter(pk=link.account_id).update(is_active=True)
    Message.objects.create(
        channel="whatsapp",
        account_id=link.account_id,
        external_id="wamid.before",
        contact_id="593990000001",
        direction=Message.DIRECTION_IN,
        message_type="text",
        text="Hola",
    )

    admin_client.delete(detail_url(link))

    account = Account.objects.get(pk=link.account_id)
    assert not account.is_active
    assert account.access_token == ""
    assert Message.objects.filter(account=account, text="Hola").count() == 1


def incoming(phone_number_id, wamid):
    """A WhatsApp message with its own id, so deduplication never hides it."""
    payload = copy.deepcopy(whatsapp_message_for(phone_number_id))
    payload["entry"][0]["changes"][0]["value"]["messages"][0]["id"] = wamid
    return payload


def test_messages_for_a_disconnected_account_are_no_longer_stored(
    admin_client, client, tenant, meta_app
):
    link = add_account(tenant, meta_app, "111")
    post_signed(client, meta_app, incoming("111", "wamid.while-connected"))
    assert Message.objects.filter(external_id="wamid.while-connected").exists()

    admin_client.delete(detail_url(link))
    response = post_signed(client, meta_app, incoming("111", "wamid.after-disconnecting"))

    assert response.status_code == 200
    assert not Message.objects.filter(external_id="wamid.after-disconnecting").exists()


def test_a_disconnected_account_can_be_connected_again_as_a_new_one(
    admin_client, client, tenant, meta_app
):
    SharedMetaApp.objects.create(app=meta_app)
    old = add_account(tenant, meta_app, "1234567890")
    post_signed(client, meta_app, incoming("1234567890", "wamid.old-history"))
    admin_client.delete(detail_url(old))

    response = connect(admin_client, external_id="1234567890")

    assert response.status_code == 201
    assert response.data["data"]["id"] != str(old.id)
    listed = admin_client.get(ACCOUNTS_URL).data["data"]
    assert [account["id"] for account in listed] == [response.data["data"]["id"]]
    new_account = ChannelAccount.objects.get(pk=response.data["data"]["id"]).account
    assert new_account.pk != old.account_id
    assert not Message.objects.filter(account=new_account).exists()
    assert Message.objects.filter(
        account_id=old.account_id, external_id="wamid.old-history"
    ).exists()


@pytest.mark.parametrize("role", [Membership.Role.AGENT, Membership.Role.SUPERVISOR])
def test_agents_and_supervisors_cannot_disconnect_an_account(tenant, meta_app, role):
    link = add_account(tenant, meta_app, "111")
    member_client = client_for(add_member(tenant, "member@acme.test", role))

    response = member_client.delete(detail_url(link))

    assert response.status_code == 403
    account = Account.objects.get(pk=link.account_id)
    assert (account.external_id, account.access_token) == ("111", TOKEN)
    assert not ChannelAccount.all_objects.get(pk=link.pk).is_deleted


def test_disconnecting_an_account_of_another_business_answers_not_found(admin_client, meta_app):
    theirs = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "222")

    response = admin_client.delete(detail_url(theirs))

    assert response.status_code == 404
    account = Account.objects.get(pk=theirs.account_id)
    assert (account.external_id, account.access_token) == ("222", TOKEN)
    assert not ChannelAccount.all_objects.get(pk=theirs.pk).is_deleted


def test_api_docs_describe_disconnecting_an_account():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema["components"]["schemas"]

    operation = schema["paths"][f"{ACCOUNTS_URL}{{account_id}}/"]["delete"]

    body = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    response = components[body.rsplit("/", 1)[1]]
    assert set(response["properties"]) == {"success", "message"}


def test_a_disconnected_account_also_loses_its_ai_api_key(admin_client, tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    Account.objects.filter(pk=link.account_id).update(ai_api_key="sk-secret-llm-key")

    admin_client.delete(detail_url(link))

    assert Account.objects.get(pk=link.account_id).ai_api_key == ""


@pytest.mark.parametrize("external_id", ["1234567890", "9" * 64])
def test_a_disconnected_account_keeps_its_original_id_in_a_traceable_form(
    admin_client, tenant, meta_app, external_id
):
    link = add_account(tenant, meta_app, external_id)

    admin_client.delete(detail_url(link))

    archived = Account.objects.get(pk=link.account_id).external_id
    assert archived.startswith(f"{external_id[:40]}#disconnected-")
    assert archived != external_id
    assert len(archived) <= 64


def test_disconnecting_an_account_twice_answers_not_found_the_second_time(
    admin_client, tenant, meta_app
):
    link = add_account(tenant, meta_app, "111")
    assert admin_client.delete(detail_url(link)).status_code == 200

    response = admin_client.delete(detail_url(link))

    assert response.status_code == 404


def test_editing_and_disconnecting_lock_the_account_so_they_never_run_together(
    admin_client, tenant, meta_app
):
    link = add_account(tenant, meta_app, "111")
    other = add_account(tenant, meta_app, "222")

    with CaptureQueriesContext(connection) as edit:
        admin_client.patch(detail_url(link), {"name": "Night shift"}, format="json")
    with CaptureQueriesContext(connection) as disconnect:
        admin_client.delete(detail_url(other))

    for queries in (edit, disconnect):
        assert any("FOR UPDATE" in query["sql"] for query in queries.captured_queries)
