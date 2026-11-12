"""
Tests for listing a business's channel accounts and editing them, never
showing their secrets.
"""

from unittest import mock

import pytest
from django.db import connection
from drf_spectacular.generators import SchemaGenerator
from wanps.messaging.models import Account, App

from apps.channels.models import ChannelAccount
from apps.channels.serializers import UpdateAccountSerializer
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

ACCOUNTS_URL = "/api/v1/channels/accounts/"
TOKEN = "EAAG-secret-token"


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def admin_client(tenant):
    return client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


def add_account(tenant, meta_app, external_id, name="Front desk", channel="whatsapp"):
    """An account already connected to the business, as POSTing to the API leaves it."""
    account = Account.objects.create(
        app=meta_app,
        channel=channel,
        name=name,
        external_id=external_id,
        business_id="998877",
        access_token=TOKEN,
        is_active=False,
    )
    return ChannelAccount.objects.create(tenant=tenant, account=account)


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_member_lists_only_their_business_accounts(tenant, meta_app, role):
    mine = add_account(tenant, meta_app, "111", name="Front desk")
    add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "222", name="Rival desk")
    member_client = client_for(add_member(tenant, "member@acme.test", role))

    response = member_client.get(ACCOUNTS_URL)

    assert response.status_code == 200
    assert response.data["data"] == [
        {
            "id": str(mine.id),
            "channel": "whatsapp",
            "name": "Front desk",
            "external_id": "111",
            "business_id": "998877",
            "is_active": False,
            "instructions": "",
        }
    ]
    assert TOKEN not in str(response.data)


def detail_url(link):
    return f"{ACCOUNTS_URL}{link.id}/"


def test_admin_renames_an_account(admin_client, tenant, meta_app):
    link = add_account(tenant, meta_app, "111", name="Front desk")

    response = admin_client.patch(detail_url(link), {"name": "Night shift"}, format="json")

    assert response.status_code == 200
    assert response.data["data"] == {
        "id": str(link.id),
        "channel": "whatsapp",
        "name": "Night shift",
        "external_id": "111",
        "business_id": "998877",
        "is_active": False,
        "instructions": "",
    }
    assert Account.objects.get(external_id="111").name == "Night shift"


def test_admin_replaces_the_access_token_and_it_is_stored_encrypted(admin_client, tenant, meta_app):
    link = add_account(tenant, meta_app, "111")

    response = admin_client.patch(
        detail_url(link), {"access_token": "EAAG-new-token"}, format="json"
    )

    assert response.status_code == 200
    assert "EAAG-new-token" not in str(response.data)
    assert "access_token" not in response.data["data"]
    with connection.cursor() as cursor:
        cursor.execute("SELECT access_token FROM messaging_account")
        (stored,) = cursor.fetchone()
    assert "EAAG-new-token" not in stored
    assert Account.objects.get(external_id="111").access_token == "EAAG-new-token"


@pytest.mark.parametrize("role", [Membership.Role.AGENT, Membership.Role.SUPERVISOR])
def test_agents_and_supervisors_cannot_edit_an_account(tenant, meta_app, role):
    link = add_account(tenant, meta_app, "111", name="Front desk")
    member_client = client_for(add_member(tenant, "member@acme.test", role))

    response = member_client.patch(
        detail_url(link), {"name": "Hijacked", "access_token": "EAAG-new-token"}, format="json"
    )

    assert response.status_code == 403
    account = Account.objects.get(external_id="111")
    assert account.name == "Front desk"
    assert account.access_token == TOKEN


def test_editing_an_account_of_another_business_answers_not_found(admin_client, meta_app):
    rival = Tenant.objects.create(name="Rival Clinic")
    theirs = add_account(rival, meta_app, "222", name="Rival desk")

    response = admin_client.patch(
        detail_url(theirs), {"name": "Hijacked", "access_token": "EAAG-new-token"}, format="json"
    )

    assert response.status_code == 404
    account = Account.objects.get(external_id="222")
    assert account.name == "Rival desk"
    assert account.access_token == TOKEN


def test_channel_external_id_and_business_id_cannot_be_changed(admin_client, tenant, meta_app):
    link = add_account(tenant, meta_app, "111", channel="whatsapp")
    other_app = App.objects.create(name="Other", app_secret="s", verify_token="v")

    response = admin_client.patch(
        detail_url(link),
        {
            "channel": "instagram",
            "external_id": "999",
            "business_id": "000",
            "app": other_app.pk,
        },
        format="json",
    )

    assert response.status_code == 200
    account = Account.objects.get(pk=link.account_id)
    assert (account.channel, account.external_id, account.business_id) == (
        "whatsapp",
        "111",
        "998877",
    )
    assert account.app == meta_app


def test_api_docs_describe_listing_and_editing_accounts_without_the_token():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema["components"]["schemas"]

    def resolved(part):
        return components[part["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[1]]

    def data_of(response):
        return components[response["properties"]["data"]["$ref"].rsplit("/", 1)[1]]

    listed = resolved(schema["paths"][ACCOUNTS_URL]["get"]["responses"]["200"])
    assert "access_token" not in data_of_items(components, listed)

    operation = schema["paths"][f"{ACCOUNTS_URL}{{account_id}}/"]["patch"]
    request_body = resolved(operation["requestBody"])
    assert set(request_body["properties"]) == {
        "name",
        "access_token",
        "is_active",
        "instructions",
    }
    assert "access_token" not in data_of(resolved(operation["responses"]["200"]))["properties"]


def data_of_items(components, response):
    items = response["properties"]["data"]["items"]
    return components[items["$ref"].rsplit("/", 1)[1]]["properties"]


def test_an_empty_access_token_is_rejected_and_the_current_one_is_kept(
    admin_client, tenant, meta_app
):
    link = add_account(tenant, meta_app, "111")

    response = admin_client.patch(detail_url(link), {"access_token": ""}, format="json")

    assert response.status_code == 400
    assert Account.objects.get(external_id="111").access_token == TOKEN


def test_editing_an_account_keeps_what_wanps_core_changed_in_the_meantime(
    admin_client, tenant, meta_app
):
    link = add_account(tenant, meta_app, "111")

    def core_changes_the_bot_first(serializer, attrs):
        Account.objects.filter(pk=link.account_id).update(is_active=True, system_prompt="Be kind")
        return attrs

    with mock.patch.object(
        UpdateAccountSerializer, "validate", autospec=True, side_effect=core_changes_the_bot_first
    ):
        response = admin_client.patch(detail_url(link), {"name": "Night shift"}, format="json")

    assert response.status_code == 200
    account = Account.objects.get(external_id="111")
    assert account.name == "Night shift"
    assert account.is_active
    assert account.system_prompt == "Be kind"
