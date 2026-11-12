"""
Tests for the format of API errors.
"""

import uuid

import pytest
from rest_framework.test import APIClient

from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for


@pytest.mark.django_db
def test_token_errors_have_a_plain_message_and_code():
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION="Bearer not-a-valid-token")

    response = api.get("/api/v1/accounts/users/me/")

    assert response.status_code == 401
    assert response.data["code"] == "token_not_valid"
    assert response.data["message"] == "Given token not valid for any token type"


@pytest.mark.django_db
def test_other_errors_keep_their_code():
    response = APIClient().get("/api/v1/accounts/users/me/")

    assert response.status_code == 401
    assert response.data["code"] == "not_authenticated"
    assert response.data["message"] == "Authentication credentials were not provided."


@pytest.mark.django_db
def test_a_not_found_carries_the_stable_code_not_found():
    tenant = Tenant.objects.create(name="Acme Dental")
    admin = client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))

    response = admin.patch(
        f"/api/v1/channels/accounts/{uuid.uuid4()}/", {"name": "x"}, format="json"
    )

    assert response.status_code == 404
    assert response.data["code"] == "not_found"
    assert response.data["message"] == "Resource not found."
