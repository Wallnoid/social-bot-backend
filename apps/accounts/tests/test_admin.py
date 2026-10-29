"""
Tests for the accounts admin.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


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


@pytest.mark.django_db
def test_admin_can_edit_user_without_username(staff_client):
    user = User.objects.create_user(
        email="owner@acme.test", first_name="Olivia", last_name="Owner"
    )

    response = staff_client.post(
        reverse("admin:accounts_user_change", args=[user.pk]),
        {
            "email": "owner@acme.test",
            "first_name": "Olivia",
            "last_name": "Owner-Edited",
            "is_active": "on",
        },
    )

    assert response.status_code == 302
    user.refresh_from_db()
    assert user.last_name == "Owner-Edited"
    assert user.username is None


@pytest.mark.django_db
def test_admin_stores_edited_user_email_in_lowercase(staff_client):
    user = User.objects.create_user(
        email="owner@acme.test", first_name="Olivia", last_name="Owner"
    )

    response = staff_client.post(
        reverse("admin:accounts_user_change", args=[user.pk]),
        {
            "email": "NewOwner@Acme.TEST",
            "first_name": "Olivia",
            "last_name": "Owner",
            "is_active": "on",
        },
    )

    assert response.status_code == 302
    user.refresh_from_db()
    assert user.email == "newowner@acme.test"
