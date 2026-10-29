"""
Tests for the accounts API views.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def api_client():
    """Return an unauthenticated API client."""
    return APIClient()


@pytest.fixture
def user():
    """Create and return a test user."""
    return User.objects.create_user(
        email="testuser@example.com",
        password="testpass123",
        first_name="Test",
        last_name="User",
    )


@pytest.fixture
def admin_user():
    """Create and return an admin user."""
    return User.objects.create_superuser(
        email="admin@example.com",
        password="adminpass123",
        first_name="Admin",
        last_name="User",
    )


@pytest.fixture
def authenticated_client(api_client, user):
    """Return an authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    """Return an admin-authenticated API client."""
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.mark.django_db
class TestRegisterView:
    """Tests for user registration."""

    def test_register_success(self, api_client):
        """Test successful user registration."""
        url = reverse("accounts:register")
        data = {
            "email": "newuser@example.com",
            "first_name": "New",
            "last_name": "User",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        }
        response = api_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["success"] is True
        assert User.objects.filter(email="newuser@example.com").exists()

    def test_register_password_mismatch(self, api_client):
        """Test registration fails when passwords don't match."""
        url = reverse("accounts:register")
        data = {
            "email": "newuser@example.com",
            "first_name": "New",
            "last_name": "User",
            "password": "StrongPass123!",
            "password_confirm": "DifferentPass456!",
        }
        response = api_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_duplicate_email(self, api_client, user):
        """Test registration fails with duplicate email."""
        url = reverse("accounts:register")
        data = {
            "email": user.email,
            "first_name": "New",
            "last_name": "User",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        }
        response = api_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestUserMeEndpoint:
    """Tests for the /users/me/ endpoint."""

    def test_me_authenticated(self, authenticated_client, user):
        """Test authenticated user can access their profile."""
        url = reverse("accounts:user-me")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["email"] == user.email

    def test_me_unauthenticated(self, api_client):
        """Test unauthenticated user cannot access /me/."""
        url = reverse("accounts:user-me")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_me_update(self, authenticated_client):
        """Test updating user profile via /me/."""
        url = reverse("accounts:user-me")
        data = {"first_name": "Updated", "bio": "Hello world"}
        response = authenticated_client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["first_name"] == "Updated"
        assert response.data["data"]["bio"] == "Hello world"


@pytest.mark.django_db
class TestChangePassword:
    """Tests for the change password endpoint."""

    def test_change_password_success(self, authenticated_client, user):
        """Test successful password change."""
        url = reverse("accounts:user-change-password")
        data = {
            "old_password": "testpass123",
            "new_password": "NewStrongPass456!",
            "new_password_confirm": "NewStrongPass456!",
        }
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK

        # Verify new password works
        user.refresh_from_db()
        assert user.check_password("NewStrongPass456!")

    def test_change_password_wrong_old(self, authenticated_client):
        """Test change password fails with wrong old password."""
        url = reverse("accounts:user-change-password")
        data = {
            "old_password": "wrongpassword",
            "new_password": "NewStrongPass456!",
            "new_password_confirm": "NewStrongPass456!",
        }
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestTokenEndpoints:
    """Tests for JWT token endpoints."""

    def test_obtain_token(self, api_client, user):
        """Test obtaining JWT token pair."""
        url = reverse("accounts:token_obtain_pair")
        data = {
            "email": "testuser@example.com",
            "password": "testpass123",
        }
        response = api_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data

    def test_refresh_token(self, api_client, user):
        """Test refreshing JWT token."""
        # First, obtain tokens
        obtain_url = reverse("accounts:token_obtain_pair")
        data = {"email": "testuser@example.com", "password": "testpass123"}
        obtain_response = api_client.post(obtain_url, data, format="json")
        refresh_token = obtain_response.data["refresh"]

        # Then, refresh
        refresh_url = reverse("accounts:token_refresh")
        response = api_client.post(
            refresh_url, {"refresh": refresh_token}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
