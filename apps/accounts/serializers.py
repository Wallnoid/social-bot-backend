"""
Serializers for the accounts app.

Handles serialization/deserialization of User data for the API.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for reading user data.
    Used in list and detail views.
    """

    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "bio",
            "avatar",
            "date_of_birth",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "email",
            "is_active",
            "created_at",
            "updated_at",
        ]


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for updating user profile.
    Only allows updating profile-related fields.
    """

    full_name = serializers.CharField(read_only=True)
    tenants = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "bio",
            "avatar",
            "date_of_birth",
            "tenants",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "email",
            "created_at",
            "updated_at",
        ]

    def get_tenants(self, user):
        """Businesses the user belongs to, with their role in each."""
        return [
            {"id": str(m.tenant_id), "name": m.tenant.name, "role": m.role}
            for m in user.memberships.filter(tenant__is_deleted=False).select_related(
                "tenant"
            )
        ]


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for changing the user's password.
    Requires the old password for verification.
    """

    old_password = serializers.CharField(
        required=True,
        style={"input_type": "password"},
    )
    new_password = serializers.CharField(
        required=True,
        validators=[validate_password],
        style={"input_type": "password"},
    )
    new_password_confirm = serializers.CharField(
        required=True,
        style={"input_type": "password"},
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Passwords do not match."}
            )
        return attrs

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value


class SetPasswordSerializer(serializers.Serializer):
    """
    Serializer for creating a password from the link sent by email.
    The link carries the user id (uid) and a one-time token.
    """

    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(style={"input_type": "password"})
    new_password_confirm = serializers.CharField(
        style={"input_type": "password"},
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs.pop("new_password_confirm"):
            raise serializers.ValidationError(
                {"new_password_confirm": "Passwords do not match."}
            )
        user = self._get_user(attrs["uid"])
        if (
            user is None
            or not user.is_active
            or not default_token_generator.check_token(user, attrs["token"])
        ):
            raise serializers.ValidationError(
                {"token": "The link is invalid or has expired."}
            )
        try:
            validate_password(attrs["new_password"], user)
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                {"new_password": list(error.messages)}
            ) from error
        attrs["user"] = user
        return attrs

    @staticmethod
    def _get_user(uid):
        try:
            return User.objects.get(pk=force_str(urlsafe_base64_decode(uid)))
        except (
            TypeError,
            ValueError,
            OverflowError,
            DjangoValidationError,
            User.DoesNotExist,
        ):
            return None
