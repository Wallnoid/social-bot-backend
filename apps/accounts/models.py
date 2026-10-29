"""
Custom User model.

Uses email as the primary login field instead of username.
Includes UUID primary key and additional profile fields.
"""

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import CustomUserManager


class User(AbstractUser):
    """
    Custom User model.

    Changes from default Django User:
    - UUID as primary key
    - Email is the unique identifier (not username)
    - Additional profile fields: phone, bio, avatar, date_of_birth
    - Timestamps: created_at, updated_at
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # Use email as the primary login field
    email = models.EmailField(
        "email address",
        unique=True,
        error_messages={
            "unique": "A user with that email already exists.",
        },
    )
    username = models.CharField(
        "username",
        max_length=150,
        unique=True,
        blank=True,
        null=True,
        help_text="Optional. 150 characters or fewer.",
    )

    # Profile fields
    phone = models.CharField(
        "phone number",
        max_length=20,
        blank=True,
        default="",
    )
    bio = models.TextField(
        "biography",
        max_length=500,
        blank=True,
        default="",
    )
    avatar = models.ImageField(
        "avatar",
        upload_to="avatars/%Y/%m/",
        blank=True,
        null=True,
    )
    date_of_birth = models.DateField(
        "date of birth",
        blank=True,
        null=True,
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Use email as the login field
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = CustomUserManager()

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        ordering = ["-created_at"]

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}".strip() or self.email
