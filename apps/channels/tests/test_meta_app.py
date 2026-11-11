"""
Tests for a business admin setting up the Meta App of their business.
"""

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from drf_spectacular.generators import SchemaGenerator
from wanps.messaging.models import Account, App

from apps.channels.models import SharedMetaApp
from apps.channels.tests.test_connect_account import connect
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

META_APP_URL = "/api/v1/channels/meta-app/"

SECRET = "app-secret-never-shown"
DATA = {
    "name": "Acme's Meta App",
    "app_id": "1234567890",
    "app_secret": SECRET,
    "verify_token": "verify-me-123",
}


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def admin_client(tenant):
    return client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))


def set_up(api, **overrides):
    return api.post(META_APP_URL, {**DATA, **overrides}, format="json")


def add_app(name="Someone's app", **extra):
    return App.objects.create(
        name=name, app_secret="their-secret", verify_token="their-verify", **extra
    )


def test_admin_sets_up_the_meta_app_and_gets_the_webhook_url_but_never_the_secret_or_the_token(
    admin_client, tenant
):
    response = set_up(admin_client)

    assert response.status_code == 201
    app = App.objects.get(app_id="1234567890")
    assert response.data["data"] == {
        "name": "Acme's Meta App",
        "app_id": "1234567890",
        "api_version": "v23.0",
        "is_active": True,
        "webhook_url": f"http://testserver/webhooks/meta/{app.webhook_key}/",
    }
    assert SECRET not in response.content.decode()
    assert "verify-me-123" not in response.content.decode()


def test_the_app_is_assigned_to_the_business_and_the_secret_is_kept(admin_client, tenant):
    set_up(admin_client)

    tenant.refresh_from_db()
    assert tenant.meta_app.app_secret == SECRET
    assert tenant.meta_app.verify_token == "verify-me-123"
    assert tenant.meta_app.provider == App.PROVIDER_META


@pytest.mark.parametrize("role", [Membership.Role.AGENT, Membership.Role.SUPERVISOR])
@pytest.mark.parametrize("method", ["get", "post", "patch"])
def test_agents_and_supervisors_get_403_on_read_create_and_edit(tenant, role, method):
    api = client_for(add_member(tenant, "member@acme.test", role))

    response = getattr(api, method)(META_APP_URL, DATA, format="json")

    assert response.status_code == 403
    assert not App.objects.exists()


def test_a_business_with_an_app_cannot_create_a_second_one(admin_client, tenant):
    set_up(admin_client)

    response = set_up(admin_client, name="Another", app_id="999")

    assert response.status_code == 400
    assert App.objects.count() == 1


@pytest.mark.parametrize("field", ["name", "app_id", "app_secret", "verify_token"])
def test_create_requires_name_app_id_app_secret_and_verify_token(admin_client, field):
    data = {key: value for key, value in DATA.items() if key != field}

    response = admin_client.post(META_APP_URL, data, format="json")

    assert response.status_code == 400
    assert field in response.data["errors"]
    assert not App.objects.exists()


def test_reading_shows_the_app_without_the_secret(admin_client):
    set_up(admin_client)

    response = admin_client.get(META_APP_URL)

    assert response.status_code == 200
    assert response.data["data"]["name"] == "Acme's Meta App"
    assert "app_secret" not in response.data["data"]
    assert "verify_token" not in response.data["data"]
    assert SECRET not in response.content.decode()
    assert "verify-me-123" not in response.content.decode()


def test_reading_without_an_app_answers_null(admin_client):
    response = admin_client.get(META_APP_URL)

    assert response.status_code == 200
    assert response.data == {"success": True, "data": None}


def test_editing_changes_the_data_and_keeps_the_secret_when_it_is_not_sent(admin_client, tenant):
    set_up(admin_client)

    response = admin_client.patch(
        META_APP_URL,
        {"name": "Renamed", "verify_token": "new-verify", "api_version": "v24.0"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["data"]["name"] == "Renamed"
    assert response.data["data"]["api_version"] == "v24.0"
    tenant.refresh_from_db()
    assert tenant.meta_app.verify_token == "new-verify"
    assert tenant.meta_app.app_secret == SECRET

    admin_client.patch(META_APP_URL, {"app_secret": "rotated"}, format="json")

    tenant.meta_app.refresh_from_db()
    assert tenant.meta_app.app_secret == "rotated"


def test_deactivating_the_app_stops_connecting_accounts(admin_client):
    set_up(admin_client)
    assert connect(admin_client).status_code == 201

    admin_client.patch(META_APP_URL, {"is_active": False}, format="json")
    response = connect(admin_client, external_id="555")

    assert response.status_code == 400
    assert "not set up" in str(response.data["message"]) + str(response.data.get("errors", ""))


def test_an_account_connects_to_the_app_of_the_business_and_not_to_another(admin_client, tenant):
    SharedMetaApp.objects.create(app=add_app("Social Bot"))
    set_up(admin_client)

    response = connect(admin_client)

    assert response.status_code == 201
    account = Account.objects.get(external_id="1234567890")
    tenant.refresh_from_db()
    assert account.app == tenant.meta_app
    assert account.app.name == "Acme's Meta App"


def test_a_business_never_reads_or_edits_the_app_of_another(admin_client, tenant):
    rival = Tenant.objects.create(name="Rival Clinic", meta_app=add_app("Rival's app"))
    add_member(rival, "boss@rival.test", Membership.Role.ADMIN)

    read = admin_client.get(META_APP_URL)
    edit = admin_client.patch(META_APP_URL, {"name": "Hijacked"}, format="json")

    assert read.data == {"success": True, "data": None}
    assert edit.status_code == 404
    rival.refresh_from_db()
    assert rival.meta_app.name == "Rival's app"


def test_an_app_that_other_businesses_use_cannot_be_edited_from_here(admin_client, tenant):
    shared = add_app("Used by two")
    tenant.meta_app = shared
    tenant.save()
    Tenant.objects.create(name="Rival Clinic", meta_app=shared)

    response = admin_client.patch(META_APP_URL, {"name": "Changed"}, format="json")

    assert response.status_code == 403
    shared.refresh_from_db()
    assert shared.name == "Used by two"


def test_the_webhook_url_given_verifies_with_the_verify_token(admin_client):
    url = set_up(admin_client).data["data"]["webhook_url"].replace("http://testserver", "")

    ok = Client().get(
        url, {"hub.mode": "subscribe", "hub.verify_token": "verify-me-123", "hub.challenge": "777"}
    )
    wrong = Client().get(
        url, {"hub.mode": "subscribe", "hub.verify_token": "other", "hub.challenge": "777"}
    )

    assert (ok.status_code, ok.content) == (200, b"777")
    assert wrong.status_code == 403


def test_the_api_docs_describe_the_endpoint_without_the_secret():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema["components"]["schemas"]

    def resolved(part):
        return components[part["content"]["application/json"]["schema"]["$ref"].rsplit("/", 1)[1]]

    operations = schema["paths"][META_APP_URL]
    assert set(operations) >= {"get", "post", "patch"}
    assert "app_secret" in resolved(operations["post"]["requestBody"])["properties"]
    created = resolved(operations["post"]["responses"]["201"])
    data = components[created["properties"]["data"]["$ref"].rsplit("/", 1)[1]]
    assert "app_secret" not in data["properties"]
    assert data["properties"]["webhook_url"]["type"] == "string"


def test_the_shared_app_of_the_platform_cannot_be_edited_from_here(admin_client, tenant):
    platform = add_app("Social Bot")
    SharedMetaApp.objects.create(app=platform)
    tenant.meta_app = platform
    tenant.save()

    response = admin_client.patch(META_APP_URL, {"is_active": False}, format="json")

    assert response.status_code == 403
    platform.refresh_from_db()
    assert platform.is_active is True


@pytest.mark.parametrize("platform_wide", [True, False])
def test_a_business_using_an_app_of_others_sees_only_its_name_and_state(
    admin_client, tenant, platform_wide
):
    used = add_app("Social Bot")
    if platform_wide:
        SharedMetaApp.objects.create(app=used)
    else:
        Tenant.objects.create(name="Rival Clinic", meta_app=used)
    tenant.meta_app = used
    tenant.save()

    response = admin_client.get(META_APP_URL)

    assert response.status_code == 200
    assert response.data["data"] == {"name": "Social Bot", "is_active": True, "shared": True}
    assert used.webhook_key not in response.content.decode()


def test_two_apps_cannot_have_the_same_app_id(admin_client, tenant):
    add_app("Rival's app", app_id="1234567890")

    created = set_up(admin_client)
    other = Tenant.objects.create(name="Other Clinic")
    other_admin = client_for(add_member(other, "boss@other.test", Membership.Role.ADMIN))
    set_up(other_admin, app_id="555")
    edited = other_admin.patch(META_APP_URL, {"app_id": "1234567890"}, format="json")

    assert created.status_code == 400
    assert "app_id" in created.data["errors"]
    assert edited.status_code == 400
    assert "Rival" not in str(created.data) + str(edited.data)
    assert App.objects.filter(app_id="1234567890").count() == 1


def test_editing_locks_the_app_while_it_is_checked(admin_client):
    set_up(admin_client)

    with CaptureQueriesContext(connection) as queries:
        admin_client.patch(META_APP_URL, {"name": "Renamed"}, format="json")

    assert any("FOR NO KEY UPDATE" in query["sql"] for query in queries)
