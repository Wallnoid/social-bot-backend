"""
Tests for the accounts User model.
"""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    """Tests for the custom User model."""

    def test_create_user(self):
        """Test creating a regular user with email."""
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
        )
        assert user.email == "test@example.com"
        assert user.check_password("testpass123")
        assert user.is_active is True
        assert user.is_staff is False
        assert user.is_superuser is False

    def test_create_superuser(self):
        """Test creating a superuser."""
        user = User.objects.create_superuser(
            email="admin@example.com",
            password="adminpass123",
            first_name="Admin",
            last_name="User",
        )
        assert user.email == "admin@example.com"
        assert user.is_active is True
        assert user.is_staff is True
        assert user.is_superuser is True

    def test_create_user_without_email_raises(self):
        """Test that creating a user without email raises ValueError."""
        with pytest.raises(ValueError, match="Email"):
            User.objects.create_user(
                email="",
                password="testpass123",
            )

    def test_user_str(self):
        """Test string representation of user."""
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        assert str(user) == "test@example.com"

    def test_user_full_name(self):
        """Test full_name property."""
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            first_name="John",
            last_name="Doe",
        )
        assert user.full_name == "John Doe"

    def test_user_full_name_fallback_to_email(self):
        """Test full_name falls back to email when names are empty."""
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        assert user.full_name == "test@example.com"

    def test_user_uuid_primary_key(self):
        """Test that user has a UUID primary key."""
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        assert user.id is not None
        assert len(str(user.id)) == 36  # UUID format

    def test_email_is_normalized(self):
        """Test that email is normalized (lowercase domain)."""
        user = User.objects.create_user(
            email="test@EXAMPLE.COM",
            password="testpass123",
        )
        assert user.email == "test@example.com"

    def test_user_timestamps(self):
        """Test that created_at and updated_at are set."""
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
        )
        assert user.created_at is not None
        assert user.updated_at is not None
