"""
Tests for connecting a business's own WhatsApp number, Messenger page or
Instagram account.
"""

import hashlib
import hmac
import json
from unittest import mock

import pytest
from django.db import connection
from drf_spectacular.generators import SchemaGenerator
from wanps.messaging.models import Account, App, Message

from apps.channels.models import ChannelAccount, SharedMetaApp
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

ACCOUNTS_URL = "/api/v1/channels/accounts/"


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def admin_client(tenant):
    return client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))


def add_app(name, is_active=True):
    return App.objects.create(
        name=name, app_secret="app-secret", verify_token="verify-token", is_active=is_active
    )


def connect(api, **overrides):
    data = {
        "channel": "whatsapp",
        "name": "Acme front desk",
        "external_id": "1234567890",
        "business_id": "998877",
        "access_token": "EAAG-secret-token",
    }
    data.update(overrides)
    return api.post(ACCOUNTS_URL, data, format="json")


def test_admin_connects_an_account_on_the_business_meta_app(admin_client, tenant):
    tenant.meta_app = add_app("Acme's own app")
    tenant.save()

    response = connect(admin_client)

    assert response.status_code == 201
    account = Account.objects.get(channel="whatsapp", external_id="1234567890")
    assert account.app == tenant.meta_app
    assert account.name == "Acme front desk"
    assert account.business_id == "998877"
    link = ChannelAccount.objects.get(account=account)
    assert link.tenant == tenant
    assert response.data["data"] == {
        "id": str(link.id),
        "channel": "whatsapp",
        "name": "Acme front desk",
        "external_id": "1234567890",
        "business_id": "998877",
        "is_active": False,
    }


def test_without_its_own_meta_app_the_account_uses_the_shared_one(admin_client):
    shared = add_app("Social Bot")
    SharedMetaApp.objects.create(app=shared)

    response = connect(admin_client)

    assert response.status_code == 201
    assert Account.objects.get(external_id="1234567890").app == shared


def test_the_business_meta_app_wins_over_the_shared_one(admin_client, tenant):
    SharedMetaApp.objects.create(app=add_app("Social Bot"))
    tenant.meta_app = add_app("Acme's own app")
    tenant.save()

    response = connect(admin_client)

    assert response.status_code == 201
    assert Account.objects.get(external_id="1234567890").app.name == "Acme's own app"


def test_an_inactive_business_meta_app_is_rejected_even_with_a_shared_one(admin_client, tenant):
    # Meta sends that business's events to its own app, never to the shared one
    SharedMetaApp.objects.create(app=add_app("Social Bot"))
    tenant.meta_app = add_app("Acme's own app", is_active=False)
    tenant.save()

    response = connect(admin_client)

    assert response.status_code == 400
    assert "not set up" in response.data["message"]
    assert not Account.objects.exists()


def test_without_any_active_meta_app_the_connection_is_rejected(admin_client, tenant):
    SharedMetaApp.objects.create(app=add_app("Social Bot", is_active=False))
    tenant.meta_app = add_app("Acme's own app", is_active=False)
    tenant.save()

    response = connect(admin_client)

    assert response.status_code == 400
    assert "not set up" in response.data["message"]
    assert not Account.objects.exists()
    assert not ChannelAccount.objects.exists()


def test_the_access_token_is_never_returned_and_is_stored_encrypted(admin_client):
    SharedMetaApp.objects.create(app=add_app("Social Bot"))

    response = connect(admin_client, access_token="EAAG-secret-token")

    assert response.status_code == 201
    assert "EAAG-secret-token" not in str(response.data)
    assert "access_token" not in response.data["data"]
    with connection.cursor() as cursor:
        cursor.execute("SELECT access_token FROM messaging_account")
        (stored,) = cursor.fetchone()
    assert "EAAG-secret-token" not in stored
    assert Account.objects.get().access_token == "EAAG-secret-token"


def whatsapp_message_for(phone_number_id):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "998877",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550000000",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [{"profile": {"name": "Ana"}, "wa_id": "593990000001"}],
                            "messages": [
                                {
                                    "from": "593990000001",
                                    "id": "wamid.connect001",
                                    "timestamp": "1699000000",
                                    "type": "text",
                                    "text": {"body": "Hola"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def post_signed(client, app, payload):
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(app.app_secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        f"/webhooks/meta/{app.webhook_key}/",
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
    )


def test_a_new_account_stores_incoming_messages_without_replying(admin_client, client):
    shared = add_app("Social Bot")
    SharedMetaApp.objects.create(app=shared)
    connect(admin_client, external_id="1234567890")

    with mock.patch("wanps.messaging.dispatch.handle_message") as handle_message:
        response = post_signed(client, shared, whatsapp_message_for("1234567890"))

    assert response.status_code == 200
    account = Account.objects.get(external_id="1234567890")
    assert not account.is_active
    assert Message.objects.filter(account=account, external_id="wamid.connect001").exists()
    handle_message.assert_not_called()


def test_an_account_already_connected_is_rejected_without_saying_who_has_it(admin_client, tenant):
    SharedMetaApp.objects.create(app=add_app("Social Bot"))
    other = Tenant.objects.create(name="Rival Clinic")
    other_admin = client_for(add_member(other, "admin@rival.test", Membership.Role.ADMIN))
    assert connect(other_admin, external_id="111").status_code == 201
    assert connect(admin_client, external_id="222").status_code == 201

    taken_by_other = connect(admin_client, external_id="111")
    taken_by_me = connect(admin_client, external_id="222")

    assert taken_by_other.status_code == taken_by_me.status_code == 400
    assert taken_by_other.data == taken_by_me.data
    assert "already connected" in str(taken_by_other.data)
    assert "Rival" not in str(taken_by_other.data)
    assert Account.objects.count() == 2


@pytest.mark.parametrize("role", [Membership.Role.AGENT, Membership.Role.SUPERVISOR])
def test_agents_and_supervisors_cannot_connect_an_account(tenant, role):
    SharedMetaApp.objects.create(app=add_app("Social Bot"))
    member_client = client_for(add_member(tenant, "member@acme.test", role))

    response = connect(member_client)

    assert response.status_code == 403
    assert not Account.objects.exists()
    assert not ChannelAccount.objects.exists()


def test_a_channel_other_than_whatsapp_messenger_or_instagram_is_rejected(admin_client):
    SharedMetaApp.objects.create(app=add_app("Social Bot"))

    response = connect(admin_client, channel="telegram")

    assert response.status_code == 400
    assert "channel" in response.data["errors"]
    assert not Account.objects.exists()


def test_two_admins_connecting_the_same_account_at_once_get_the_same_rejection(admin_client):
    SharedMetaApp.objects.create(app=add_app("Social Bot"))
    assert connect(admin_client, external_id="111").status_code == 201

    # The other request passed validation before this one was saved
    with mock.patch("rest_framework.validators.UniqueTogetherValidator.__call__"):
        response = connect(admin_client, external_id="111")

    assert response.status_code == 400
    assert "already connected" in str(response.data)
    assert Account.objects.count() == 1
    assert ChannelAccount.objects.count() == 1


def test_api_docs_describe_connecting_an_account_without_its_token_in_the_response():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema["components"]["schemas"]

    def resolved(part):
        return components[part["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[1]]

    operation = schema["paths"][ACCOUNTS_URL]["post"]
    request_body = resolved(operation["requestBody"])
    assert "access_token" in request_body["properties"]
    assert "id" not in request_body["properties"]

    created = resolved(operation["responses"]["201"])
    data = components[created["properties"]["data"]["$ref"].rsplit("/", 1)[1]]
    assert "access_token" not in data["properties"]
    assert data["properties"]["id"]["format"] == "uuid"
