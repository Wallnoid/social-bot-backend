"""
Tests for seeing my businesses and my role in each one from the profile.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.tenants.models import Membership, Tenant

User = get_user_model()

ME_URL = "/api/v1/accounts/users/me/"
PASSWORD = "StrongPass123!"


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="olivia@acme.test",
        password=PASSWORD,
        first_name="Olivia",
        last_name="Owner",
    )


@pytest.fixture
def logged_in(user):
    """Return an API client that logged in through the real login endpoint."""
    api = APIClient()
    response = api.post(
        "/api/v1/accounts/token/",
        {"email": "olivia@acme.test", "password": PASSWORD},
        format="json",
    )
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    return api


def get_tenants(api):
    return api.get(ME_URL).data["data"]["tenants"]


def test_me_shows_the_business_and_my_role(user, logged_in):
    tenant = Tenant.objects.create(name="Acme Dental")
    Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.ADMIN)

    assert get_tenants(logged_in) == [
        {"id": str(tenant.id), "name": "Acme Dental", "role": "admin"}
    ]


def test_me_lists_every_business_with_my_role_in_each(user, logged_in):
    dental = Tenant.objects.create(name="Acme Dental")
    gym = Tenant.objects.create(name="Acme Gym")
    other = Tenant.objects.create(name="Other Business")
    Membership.objects.create(tenant=dental, user=user, role=Membership.Role.ADMIN)
    Membership.objects.create(tenant=gym, user=user, role=Membership.Role.AGENT)
    stranger = User.objects.create_user(email="stranger@other.test", password=PASSWORD)
    Membership.objects.create(
        tenant=other, user=stranger, role=Membership.Role.ADMIN
    )

    tenants = get_tenants(logged_in)

    assert {t["name"]: t["role"] for t in tenants} == {
        "Acme Dental": "admin",
        "Acme Gym": "agent",
    }


def test_me_hides_a_business_after_my_membership_is_removed(user, logged_in):
    dental = Tenant.objects.create(name="Acme Dental")
    gym = Tenant.objects.create(name="Acme Gym")
    Membership.objects.create(tenant=dental, user=user, role=Membership.Role.ADMIN)
    removed = Membership.objects.create(
        tenant=gym, user=user, role=Membership.Role.AGENT
    )
    removed.delete()

    assert [t["name"] for t in get_tenants(logged_in)] == ["Acme Dental"]


def test_me_hides_a_deleted_business(user, logged_in):
    dental = Tenant.objects.create(name="Acme Dental")
    gym = Tenant.objects.create(name="Acme Gym")
    Membership.objects.create(tenant=dental, user=user, role=Membership.Role.ADMIN)
    Membership.objects.create(tenant=gym, user=user, role=Membership.Role.AGENT)
    gym.delete()

    assert [t["name"] for t in get_tenants(logged_in)] == ["Acme Dental"]


def test_me_shows_no_businesses_when_i_belong_to_none(logged_in):
    assert get_tenants(logged_in) == []


def test_me_update_response_keeps_showing_my_businesses(user, logged_in):
    tenant = Tenant.objects.create(name="Acme Dental")
    Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.ADMIN)

    response = logged_in.patch(ME_URL, {"first_name": "Olga"}, format="json")

    assert response.data["data"]["first_name"] == "Olga"
    assert response.data["data"]["tenants"] == [
        {"id": str(tenant.id), "name": "Acme Dental", "role": "admin"}
    ]
