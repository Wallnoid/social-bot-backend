"""
Tests for an admin listing, changing and removing the members of a business.
"""

import threading
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from drf_spectacular.generators import SchemaGenerator

from apps.tenants.models import Invitation, Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

User = get_user_model()

MEMBERS_URL = "/api/v1/tenants/members/"


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    """Throttle counters live in the cache; start every test from zero."""
    cache.clear()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def admin(tenant):
    return add_member(tenant, "boss@acme.test", Membership.Role.ADMIN)


@pytest.fixture
def admin_client(admin):
    return client_for(admin)


def test_admin_sees_the_members_except_themselves(admin_client, tenant):
    agent = add_member(
        tenant,
        "agent@acme.test",
        Membership.Role.AGENT,
        first_name="Ana",
        last_name="Vera",
    )

    response = admin_client.get(MEMBERS_URL)

    assert response.status_code == 200
    assert response.data["data"] == [
        {
            "id": str(agent.id),
            "first_name": "Ana",
            "last_name": "Vera",
            "email": "agent@acme.test",
            "role": "agent",
        }
    ]


def test_list_leaves_out_other_businesses_and_removed_members(admin_client, tenant):
    other_tenant = Tenant.objects.create(name="Other Clinic")
    add_member(other_tenant, "outsider@other.test", Membership.Role.AGENT)
    add_member(tenant, "removed@acme.test", Membership.Role.AGENT).soft_delete()

    response = admin_client.get(MEMBERS_URL)

    assert response.data["data"] == []


def test_an_agent_cannot_see_the_members(tenant):
    api = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    response = api.get(MEMBERS_URL)

    assert response.status_code == 403
    assert "data" not in response.data


def member_url(member):
    return f"{MEMBERS_URL}{member.id}/"


def test_changed_role_applies_on_the_member_next_request(admin_client, tenant):
    agent = add_member(tenant, "agent@acme.test", Membership.Role.AGENT)
    agent_client = client_for(agent)

    response = admin_client.patch(member_url(agent), {"role": "supervisor"}, format="json")

    assert response.status_code == 200
    assert response.data["data"]["role"] == "supervisor"
    current = agent_client.get("/api/v1/tenants/current/")
    assert current.data["data"]["role"] == "supervisor"


def test_admin_can_change_another_admin(admin_client, tenant):
    other_admin = add_member(tenant, "other@acme.test", Membership.Role.ADMIN)

    response = admin_client.patch(member_url(other_admin), {"role": "agent"}, format="json")

    assert response.status_code == 200
    other_admin.refresh_from_db()
    assert other_admin.role == "agent"


@pytest.mark.parametrize("body", [{"role": "owner"}, {}])
def test_change_rejects_an_invalid_or_missing_role(admin_client, tenant, body):
    agent = add_member(tenant, "agent@acme.test", Membership.Role.AGENT)

    response = admin_client.patch(member_url(agent), body, format="json")

    assert response.status_code == 400
    assert "role" in response.data["errors"]
    agent.refresh_from_db()
    assert agent.role == "agent"


def test_removed_member_loses_access_on_their_next_request(admin_client, tenant):
    agent = add_member(tenant, "agent@acme.test", Membership.Role.AGENT)
    agent_client = client_for(agent)
    assert agent_client.get("/api/v1/tenants/current/").status_code == 200

    response = admin_client.delete(member_url(agent))

    assert response.status_code == 200
    assert response.data["success"] is True
    assert agent_client.get("/api/v1/tenants/current/").status_code == 404


def test_removed_member_keeps_their_account_and_other_businesses(admin_client, tenant):
    agent = add_member(tenant, "agent@acme.test", Membership.Role.AGENT)
    other_tenant = Tenant.objects.create(name="Other Clinic")
    other_membership = Membership.objects.create(
        tenant=other_tenant, user=agent.user, role=Membership.Role.SUPERVISOR
    )

    admin_client.delete(member_url(agent))

    current = client_for(other_membership).get("/api/v1/tenants/current/")
    assert current.status_code == 200
    assert current.data["data"]["name"] == "Other Clinic"


def test_admin_can_remove_another_admin(admin_client, tenant):
    other_admin = add_member(tenant, "other@acme.test", Membership.Role.ADMIN)

    response = admin_client.delete(member_url(other_admin))

    assert response.status_code == 200
    assert not Membership.objects.filter(pk=other_admin.pk).exists()


def test_removed_member_can_be_invited_again(admin_client, tenant):
    agent = add_member(tenant, "agent@acme.test", Membership.Role.AGENT)
    admin_client.delete(member_url(agent))

    response = admin_client.post(
        "/api/v1/tenants/invitations/",
        {"email": "agent@acme.test", "role": "agent"},
        format="json",
    )

    assert response.status_code == 201


def act(api, action, member):
    if action == "patch":
        return api.patch(member_url(member), {"role": "supervisor"}, format="json")
    return api.delete(member_url(member))


def assert_unchanged(member):
    role = member.role
    member.refresh_from_db()
    assert member.role == role
    assert member.is_deleted is False


@pytest.mark.parametrize("action", ["patch", "delete"])
@pytest.mark.parametrize("role", [Membership.Role.AGENT, Membership.Role.SUPERVISOR])
def test_agent_and_supervisor_cannot_change_or_remove(tenant, role, action):
    api = client_for(add_member(tenant, "member@acme.test", role))
    target = add_member(tenant, "target@acme.test", Membership.Role.AGENT)

    response = act(api, action, target)

    assert response.status_code == 403
    assert_unchanged(target)


@pytest.mark.parametrize("action", ["patch", "delete"])
def test_cannot_change_or_remove_a_member_of_another_business(admin_client, action):
    other_tenant = Tenant.objects.create(name="Other Clinic")
    outsider = add_member(other_tenant, "outsider@other.test", Membership.Role.AGENT)

    response = act(admin_client, action, outsider)

    assert response.status_code == 404
    assert_unchanged(outsider)


@pytest.mark.parametrize("action", ["patch", "delete"])
def test_admin_cannot_change_or_remove_themselves(admin_client, admin, action):
    response = act(admin_client, action, admin)

    assert response.status_code == 404
    assert_unchanged(admin)


@pytest.mark.parametrize("action", ["patch", "delete"])
def test_cannot_change_or_remove_an_already_removed_member(admin_client, tenant, action):
    removed = add_member(tenant, "removed@acme.test", Membership.Role.AGENT)
    removed.soft_delete()

    response = act(admin_client, action, removed)

    assert response.status_code == 404


@pytest.mark.parametrize("action", ["patch", "delete"])
def test_admin_demoted_at_the_same_time_cannot_act(admin_client, admin, tenant, action):
    target = add_member(tenant, "target@acme.test", Membership.Role.ADMIN)
    Membership.objects.filter(pk=admin.pk).update(role=Membership.Role.AGENT)

    # The other admin's change lands after this request passed its permission check
    with mock.patch("apps.tenants.permissions.IsTenantAdmin.has_permission", return_value=True):
        response = act(admin_client, action, target)

    assert response.status_code == 403
    assert_unchanged(target)


def add_invitation(tenant, invited_by, role=Membership.Role.ADMIN):
    return Invitation.objects.create(
        tenant=tenant, email="second@acme.test", role=role, invited_by=invited_by
    )


def lookup_status(api, invitation):
    cache.clear()  # Lookups are limited per minute, and a test may need several
    return api.post(
        "/api/v1/tenants/invitations/lookup/", {"token": invitation.token}, format="json"
    ).status_code


@pytest.mark.parametrize("role", ["agent", "supervisor"])
def test_demoting_an_admin_cancels_the_invitations_they_sent(admin_client, tenant, role):
    other_admin = add_member(tenant, "other@acme.test", Membership.Role.ADMIN)
    invitation = add_invitation(tenant, other_admin.user)

    admin_client.patch(member_url(other_admin), {"role": role}, format="json")

    assert lookup_status(admin_client, invitation) == 400


def test_removing_an_admin_cancels_the_invitations_they_sent(admin_client, tenant):
    other_admin = add_member(tenant, "other@acme.test", Membership.Role.ADMIN)
    invitation = add_invitation(tenant, other_admin.user, role=Membership.Role.AGENT)

    admin_client.delete(member_url(other_admin))

    assert lookup_status(admin_client, invitation) == 400


def test_invitations_survive_other_changes(admin_client, admin, tenant):
    other_admin = add_member(tenant, "other@acme.test", Membership.Role.ADMIN)
    agent = add_member(tenant, "agent@acme.test", Membership.Role.AGENT)
    other_tenant = Tenant.objects.create(name="Other Clinic")
    still_admin = add_invitation(tenant, other_admin.user)
    from_someone_else = Invitation.objects.create(
        tenant=tenant, email="third@acme.test", role="agent", invited_by=admin.user
    )
    other_business = add_invitation(other_tenant, other_admin.user)

    admin_client.patch(member_url(other_admin), {"role": "admin"}, format="json")
    admin_client.delete(member_url(agent))

    assert lookup_status(admin_client, still_admin) == 200
    assert lookup_status(admin_client, from_someone_else) == 200
    assert lookup_status(admin_client, other_business) == 200

    admin_client.delete(member_url(other_admin))

    assert lookup_status(admin_client, still_admin) == 400
    assert lookup_status(admin_client, from_someone_else) == 200
    assert lookup_status(admin_client, other_business) == 200


@pytest.mark.parametrize("action", ["patch", "delete"])
def test_business_deleted_during_the_request_gets_a_404(admin_client, admin, tenant, action):
    target = add_member(tenant, "target@acme.test", Membership.Role.AGENT)
    Tenant.objects.get(pk=tenant.pk).soft_delete()

    def stale_check(self, request, view):
        request.tenant = tenant
        request.membership = admin
        return True

    with mock.patch("apps.tenants.permissions.HasActiveTenant.has_permission", new=stale_check):
        response = act(admin_client, action, target)

    assert response.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_two_admins_demoting_each_other_leave_one_admin():
    tenant = Tenant.objects.create(name="Acme Dental")
    first = add_member(tenant, "first@acme.test", Membership.Role.ADMIN)
    second = add_member(tenant, "second@acme.test", Membership.Role.ADMIN)
    first_client, second_client = client_for(first), client_for(second)

    def demote(api, target, barrier):
        barrier.wait()
        api.patch(member_url(target), {"role": "agent"}, format="json")
        connection.close()

    for _ in range(20):
        Membership.objects.filter(tenant=tenant).update(role=Membership.Role.ADMIN)
        barrier = threading.Barrier(2)
        threads = [
            threading.Thread(target=demote, args=(first_client, second, barrier)),
            threading.Thread(target=demote, args=(second_client, first, barrier)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert Membership.objects.filter(tenant=tenant, role=Membership.Role.ADMIN).count() == 1


def json_schema(part):
    return part["content"]["application/json"]["schema"]


def resolved(schema, reference):
    return schema["components"]["schemas"][reference["$ref"].rsplit("/", 1)[1]]


def test_api_docs_describe_the_member_endpoints():
    schema = SchemaGenerator().get_schema(request=None, public=True)

    listing = schema["paths"][MEMBERS_URL]["get"]["responses"]["200"]
    assert resolved(schema, json_schema(listing))["properties"]["data"]["type"] == "array"

    detail = schema["paths"][f"{MEMBERS_URL}{{member_id}}/"]
    assert json_schema(detail["patch"]["requestBody"])["required"] == ["role"]
    changed = resolved(schema, json_schema(detail["patch"]["responses"]["200"]))
    assert "data" in changed["properties"]

    assert list(detail["delete"]["responses"]) == ["200"]
    removed = resolved(schema, json_schema(detail["delete"]["responses"]["200"]))
    assert "message" in removed["properties"]
