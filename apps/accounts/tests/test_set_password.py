"""
Tests for creating a password from the link emailed to a new first admin.
"""

import re
from datetime import datetime, timedelta
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()

SET_PASSWORD_URL = "/api/v1/accounts/set-password/"


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    """Throttle counters live in the cache; start every test from zero."""
    cache.clear()


@pytest.fixture
def staff_client(client):
    """Return a Django test client logged in as a superuser."""
    superuser = User.objects.create_superuser(
        email="staff@example.com",
        password="staffpass123",
        first_name="Staff",
        last_name="User",
    )
    client.force_login(superuser)
    return client


@pytest.fixture
def emailed_link(staff_client, settings, mailoutbox):
    """Create a business with a new first admin and return the link they get."""
    settings.FRONTEND_URL = "https://app.example.test"
    staff_client.post(
        reverse("admin:tenants_tenant_add"),
        {
            "name": "Acme Dental",
            "admin_email": "owner@acme.test",
            "admin_first_name": "Olivia",
            "admin_last_name": "Owner",
        },
    )
    match = re.search(r"uid=([^&\s]+)&token=(\S+)", mailoutbox[0].body)
    return {"uid": match.group(1), "token": match.group(2)}


@pytest.mark.django_db
def test_set_password_with_link_from_email_allows_login(emailed_link):
    api = APIClient()

    response = api.post(
        SET_PASSWORD_URL,
        {
            **emailed_link,
            "new_password": "StrongPass123!",
            "new_password_confirm": "StrongPass123!",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK

    login = api.post(
        "/api/v1/accounts/token/",
        {"email": "owner@acme.test", "password": "StrongPass123!"},
        format="json",
    )
    assert login.status_code == status.HTTP_200_OK
    assert "access" in login.data


@pytest.mark.django_db
def test_set_password_link_cannot_be_used_twice(emailed_link):
    api = APIClient()
    api.post(
        SET_PASSWORD_URL,
        {
            **emailed_link,
            "new_password": "StrongPass123!",
            "new_password_confirm": "StrongPass123!",
        },
        format="json",
    )

    response = api.post(
        SET_PASSWORD_URL,
        {
            **emailed_link,
            "new_password": "AnotherPass456!",
            "new_password_confirm": "AnotherPass456!",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "The link is invalid or has expired." in str(response.data)
    login = api.post(
        "/api/v1/accounts/token/",
        {"email": "owner@acme.test", "password": "StrongPass123!"},
        format="json",
    )
    assert login.status_code == status.HTTP_200_OK


def days_from_now(days):
    """Make the token generator believe `days` days have passed."""
    return mock.patch.object(
        PasswordResetTokenGenerator,
        "_now",
        lambda self: datetime.now() + timedelta(days=days),
    )


@pytest.mark.django_db
def test_set_password_link_still_works_after_six_days(emailed_link):
    with days_from_now(6):
        response = APIClient().post(
            SET_PASSWORD_URL,
            {
                **emailed_link,
                "new_password": "StrongPass123!",
                "new_password_confirm": "StrongPass123!",
            },
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK



@pytest.mark.django_db
def test_set_password_link_is_rejected_after_eight_days(emailed_link):
    with days_from_now(8):
        response = APIClient().post(
            SET_PASSWORD_URL,
            {
                **emailed_link,
                "new_password": "StrongPass123!",
                "new_password_confirm": "StrongPass123!",
            },
            format="json",
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "The link is invalid or has expired." in str(response.data)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "tampering",
    [
        {"token": "not-the-right-token"},
        {"uid": "not-a-valid-uid"},
    ],
    ids=["wrong_token", "wrong_uid"],
)
def test_set_password_rejects_invalid_link(emailed_link, tampering):
    response = APIClient().post(
        SET_PASSWORD_URL,
        {
            **emailed_link,
            **tampering,
            "new_password": "StrongPass123!",
            "new_password_confirm": "StrongPass123!",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "The link is invalid or has expired." in str(response.data)


@pytest.mark.django_db
def test_set_password_rejects_weak_password(emailed_link):
    api = APIClient()

    weak = api.post(
        SET_PASSWORD_URL,
        {**emailed_link, "new_password": "123", "new_password_confirm": "123"},
        format="json",
    )
    assert weak.status_code == status.HTTP_400_BAD_REQUEST
    assert "new_password" in str(weak.data)

    retry = api.post(
        SET_PASSWORD_URL,
        {
            **emailed_link,
            "new_password": "StrongPass123!",
            "new_password_confirm": "StrongPass123!",
        },
        format="json",
    )
    assert retry.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_set_password_rejects_mismatched_confirmation(emailed_link):
    api = APIClient()

    mismatch = api.post(
        SET_PASSWORD_URL,
        {
            **emailed_link,
            "new_password": "StrongPass123!",
            "new_password_confirm": "DifferentPass456!",
        },
        format="json",
    )
    assert mismatch.status_code == status.HTTP_400_BAD_REQUEST
    assert "new_password_confirm" in str(mismatch.data)

    retry = api.post(
        SET_PASSWORD_URL,
        {
            **emailed_link,
            "new_password": "StrongPass123!",
            "new_password_confirm": "StrongPass123!",
        },
        format="json",
    )
    assert retry.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_set_password_is_rate_limited(emailed_link):
    api = APIClient()
    payload = {
        **emailed_link,
        "token": "not-the-right-token",
        "new_password": "StrongPass123!",
        "new_password_confirm": "StrongPass123!",
    }

    statuses = [
        api.post(SET_PASSWORD_URL, payload, format="json").status_code
        for _ in range(6)
    ]

    assert statuses == [400, 400, 400, 400, 400, 429]



@pytest.mark.django_db
def test_set_password_rejects_deactivated_user(emailed_link):
    User.objects.filter(email="owner@acme.test").update(is_active=False)

    response = APIClient().post(
        SET_PASSWORD_URL,
        {
            **emailed_link,
            "new_password": "StrongPass123!",
            "new_password_confirm": "StrongPass123!",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "The link is invalid or has expired." in str(response.data)
    assert not User.objects.get(email="owner@acme.test").has_usable_password()


@pytest.mark.django_db
def test_set_password_rejects_password_similar_to_email(emailed_link):
    response = APIClient().post(
        SET_PASSWORD_URL,
        {
            **emailed_link,
            "new_password": "owner@acme.test",
            "new_password_confirm": "owner@acme.test",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "new_password" in str(response.data)
