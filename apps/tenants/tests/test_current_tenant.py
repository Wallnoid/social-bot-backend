"""
Tests for choosing the business I work in with the X-Tenant-ID header.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.tenants.models import Membership, Tenant

User = get_user_model()

CURRENT_URL = "/api/v1/tenants/current/"
PASSWORD = "StrongPass123!"


@pytest.fixture
def user(db):
    return User.objects.create_user(email="olivia@acme.test", password=PASSWORD)


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


@pytest.fixture
def dental(user):
    tenant = Tenant.objects.create(name="Acme Dental")
    Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.ADMIN)
    return tenant


@pytest.fixture
def gym(user):
    tenant = Tenant.objects.create(name="Acme Gym")
    Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.AGENT)
    return tenant


def current(api, tenant_id=None):
    headers = {} if tenant_id is None else {"HTTP_X_TENANT_ID": str(tenant_id)}
    return api.get(CURRENT_URL, **headers)


def test_current_shows_the_business_i_choose_and_my_role(logged_in, dental, gym):
    response = current(logged_in, dental.id)

    assert response.status_code == 200
    assert response.data["data"] == {
        "id": str(dental.id),
        "name": "Acme Dental",
        "role": "admin",
    }


def test_current_switches_when_i_send_another_business(logged_in, dental, gym):
    first = current(logged_in, dental.id)
    second = current(logged_in, gym.id)

    assert first.data["data"]["name"] == "Acme Dental"
    assert second.data["data"] == {
        "id": str(gym.id),
        "name": "Acme Gym",
        "role": "agent",
    }


def test_current_rejects_a_business_i_do_not_belong_to(logged_in, dental):
    stranger = User.objects.create_user(email="stranger@other.test", password=PASSWORD)
    other = Tenant.objects.create(name="Other Business")
    Membership.objects.create(tenant=other, user=stranger, role=Membership.Role.ADMIN)

    response = current(logged_in, other.id)

    assert response.status_code == 404
    assert response.data["success"] is False


def test_current_rejects_a_business_after_my_membership_is_removed(
    user, logged_in, dental, gym
):
    Membership.objects.get(tenant=gym, user=user).delete()

    response = current(logged_in, gym.id)

    assert response.status_code == 404
    assert current(logged_in, dental.id).status_code == 200


def test_current_rejects_a_deleted_business(logged_in, dental, gym):
    gym.delete()

    response = current(logged_in, gym.id)

    assert response.status_code == 404
    assert current(logged_in, dental.id).status_code == 200


def test_current_rejects_a_malformed_business_id(logged_in, dental):
    response = current(logged_in, "not-a-uuid")

    assert response.status_code == 404
    assert response.data["success"] is False


def test_current_asks_to_choose_when_i_have_several_and_send_none(
    logged_in, dental, gym
):
    response = current(logged_in)

    assert response.status_code == 400
    assert response.data["success"] is False
    assert "X-Tenant-ID" in str(response.data)


def test_current_uses_my_only_business_without_header(logged_in, dental):
    response = current(logged_in)

    assert response.status_code == 200
    assert response.data["data"] == {
        "id": str(dental.id),
        "name": "Acme Dental",
        "role": "admin",
    }


def test_current_requires_login():
    response = APIClient().get(CURRENT_URL)

    assert response.status_code == 401


def test_current_treats_an_empty_header_as_none_chosen(logged_in, dental):
    response = current(logged_in, "")

    assert response.status_code == 200
    assert response.data["data"]["name"] == "Acme Dental"


def test_current_says_i_have_no_business_when_i_belong_to_none(logged_in):
    response = current(logged_in)

    assert response.status_code == 404
    assert "any business" in response.data["message"]
