"""
Tests for an admin listing and cancelling the pending invitations of a business.
"""

import threading
from datetime import timedelta
from unittest import mock

import pytest
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

from apps.tenants.models import Invitation, Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

INVITATIONS_URL = "/api/v1/tenants/invitations/"


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    """Throttle counters live in the cache; start every test from zero."""
    cache.clear()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def admin(tenant):
    return add_member(
        tenant, "boss@acme.test", Membership.Role.ADMIN, first_name="Bea", last_name="Boss"
    )


@pytest.fixture
def admin_client(admin):
    return client_for(admin)


def add_invitation(tenant, invited_by, email="new@acme.test", role=Membership.Role.AGENT):
    return Invitation.objects.create(tenant=tenant, email=email, role=role, invited_by=invited_by)


def test_admin_sees_the_pending_invitations_and_who_sent_them(admin_client, admin, tenant):
    invitation = add_invitation(tenant, admin.user, role=Membership.Role.SUPERVISOR)

    response = admin_client.get(INVITATIONS_URL)

    assert response.status_code == 200
    assert response.data["data"] == [
        {
            "id": str(invitation.id),
            "email": "new@acme.test",
            "role": "supervisor",
            "invited_by": {"first_name": "Bea", "last_name": "Boss", "email": "boss@acme.test"},
            "expires_at": invitation.expires_at.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
    ]


def test_list_leaves_out_expired_used_and_other_business_invitations(admin_client, admin, tenant):
    expired = add_invitation(tenant, admin.user, email="expired@acme.test")
    Invitation.objects.filter(pk=expired.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    add_invitation(tenant, admin.user, email="used@acme.test").soft_delete()
    other_tenant = Tenant.objects.create(name="Other Clinic")
    add_invitation(other_tenant, admin.user, email="outsider@other.test")

    response = admin_client.get(INVITATIONS_URL)

    assert response.data["data"] == []


@pytest.mark.parametrize("role", [Membership.Role.AGENT, Membership.Role.SUPERVISOR])
def test_agent_and_supervisor_cannot_see_the_invitations(admin, tenant, role):
    add_invitation(tenant, admin.user)
    api = client_for(add_member(tenant, "member@acme.test", role))

    response = api.get(INVITATIONS_URL)

    assert response.status_code == 403
    assert "data" not in response.data


def test_listing_does_not_use_up_the_invitation_limit(admin_client):
    for _ in range(15):
        assert admin_client.get(INVITATIONS_URL).status_code == 200

    response = admin_client.post(
        INVITATIONS_URL, {"email": "new@acme.test", "role": "agent"}, format="json"
    )

    assert response.status_code == 201


def invitation_url(invitation):
    return f"{INVITATIONS_URL}{invitation.id}/"


def lookup_status(api, invitation):
    cache.clear()  # Lookups are limited per minute, and a test may need several
    return api.post(
        "/api/v1/tenants/invitations/lookup/", {"token": invitation.token}, format="json"
    ).status_code


def test_cancelled_invitation_link_stops_working(admin_client, admin, tenant):
    invitation = add_invitation(tenant, admin.user)
    assert lookup_status(admin_client, invitation) == 200

    response = admin_client.delete(invitation_url(invitation))

    assert response.status_code == 200
    assert response.data["success"] is True
    assert lookup_status(admin_client, invitation) == 400
    assert admin_client.get(INVITATIONS_URL).data["data"] == []


def test_email_can_be_invited_again_after_cancelling(admin_client, admin, tenant):
    invitation = add_invitation(tenant, admin.user)
    admin_client.delete(invitation_url(invitation))

    response = admin_client.post(
        INVITATIONS_URL, {"email": "new@acme.test", "role": "agent"}, format="json"
    )

    assert response.status_code == 201


def test_admin_can_cancel_another_admins_invitation(admin_client, tenant):
    other_admin = add_member(tenant, "other@acme.test", Membership.Role.ADMIN)
    invitation = add_invitation(tenant, other_admin.user)

    response = admin_client.delete(invitation_url(invitation))

    assert response.status_code == 200
    assert lookup_status(admin_client, invitation) == 400


def assert_still_pending(api, invitation):
    assert lookup_status(api, invitation) == 200


@pytest.mark.parametrize("role", [Membership.Role.AGENT, Membership.Role.SUPERVISOR])
def test_agent_and_supervisor_cannot_cancel(admin_client, admin, tenant, role):
    invitation = add_invitation(tenant, admin.user)
    api = client_for(add_member(tenant, "member@acme.test", role))

    response = api.delete(invitation_url(invitation))

    assert response.status_code == 403
    assert_still_pending(admin_client, invitation)


def test_cannot_cancel_an_invitation_of_another_business(admin_client, admin):
    other_tenant = Tenant.objects.create(name="Other Clinic")
    invitation = add_invitation(other_tenant, admin.user)

    response = admin_client.delete(invitation_url(invitation))

    assert response.status_code == 404
    assert_still_pending(admin_client, invitation)


def accept(api, invitation):
    cache.clear()
    api.post(
        "/api/v1/tenants/invitations/accept/",
        {
            "token": invitation.token,
            "first_name": "Ana",
            "last_name": "Vera",
            "new_password": "StrongPass123!",
            "new_password_confirm": "StrongPass123!",
        },
        format="json",
    )


def cancel(api, invitation):
    api.delete(invitation_url(invitation))


def expire(api, invitation):
    Invitation.objects.filter(pk=invitation.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )


@pytest.mark.parametrize("finish", [accept, cancel, expire])
def test_cannot_cancel_an_accepted_cancelled_or_expired_invitation(
    admin_client, admin, tenant, finish
):
    invitation = add_invitation(tenant, admin.user)
    finish(APIClient() if finish is accept else admin_client, invitation)

    response = admin_client.delete(invitation_url(invitation))

    assert response.status_code == 404


def test_admin_demoted_at_the_same_time_cannot_cancel(admin_client, admin, tenant):
    invitation = add_invitation(tenant, admin.user)
    Membership.objects.filter(pk=admin.pk).update(role=Membership.Role.AGENT)

    # The other admin's change lands after this request passed its permission check
    with mock.patch("apps.tenants.permissions.IsTenantAdmin.has_permission", return_value=True):
        response = admin_client.delete(invitation_url(invitation))

    assert response.status_code == 403
    assert_still_pending(admin_client, invitation)


def run_in_thread(name, request, barrier, results):
    """Store the status code, or the error, so a failing thread cannot hide behind the other."""
    barrier.wait()
    try:
        results[name] = request().status_code
    except Exception as error:  # noqa: BLE001
        results[name] = repr(error)
    finally:
        connection.close()


def accept_request(invitation):
    return lambda: APIClient().post(
        "/api/v1/tenants/invitations/accept/",
        {
            "token": invitation.token,
            "first_name": "Ana",
            "last_name": "Vera",
            "new_password": "StrongPass123!",
            "new_password_confirm": "StrongPass123!",
        },
        format="json",
    )


@pytest.mark.django_db(transaction=True)
def test_cancel_and_accept_at_the_same_time_exactly_one_succeeds():
    tenant = Tenant.objects.create(name="Acme Dental")
    admin = add_member(tenant, "boss@acme.test", Membership.Role.ADMIN)
    admin_client = client_for(admin)

    for number in range(10):
        cache.clear()
        invitation = add_invitation(tenant, admin.user, email=f"new{number}@acme.test")
        barrier = threading.Barrier(2)
        results = {}
        cancel_request = lambda invitation=invitation: admin_client.delete(  # noqa: E731
            invitation_url(invitation)
        )
        threads = [
            threading.Thread(
                target=run_in_thread,
                args=("accept", accept_request(invitation), barrier, results),
            ),
            threading.Thread(
                target=run_in_thread, args=("cancel", cancel_request, barrier, results)
            ),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Accepted first: cancelling finds nothing. Cancelled first: the link is rejected.
        assert results in ({"accept": 201, "cancel": 404}, {"accept": 400, "cancel": 200})
        joined = Membership.objects.filter(tenant=tenant, user__email=invitation.email).exists()
        assert joined is (results["accept"] == 201)


def json_schema(part):
    return part["content"]["application/json"]["schema"]


def resolved(schema, reference):
    return schema["components"]["schemas"][reference["$ref"].rsplit("/", 1)[1]]


def test_api_docs_describe_the_invitation_list_and_cancel():
    schema = SchemaGenerator().get_schema(request=None, public=True)

    listing = schema["paths"][INVITATIONS_URL]["get"]["responses"]["200"]
    assert resolved(schema, json_schema(listing))["properties"]["data"]["type"] == "array"

    cancelled = schema["paths"][f"{INVITATIONS_URL}{{invitation_id}}/"]["delete"]["responses"]
    assert list(cancelled) == ["200"]
    assert "message" in resolved(schema, json_schema(cancelled["200"]))["properties"]
