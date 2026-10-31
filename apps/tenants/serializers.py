"""
Serializers for the tenants app.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotAuthenticated, PermissionDenied

from .models import Invitation, Membership

User = get_user_model()


class InvitationSerializer(serializers.ModelSerializer):
    """Serializer for inviting a person; the token is never returned."""

    class Meta:
        model = Invitation
        fields = ["id", "email", "role", "expires_at"]
        read_only_fields = ["id", "expires_at"]

    def validate_email(self, value):
        email = value.lower()
        if Membership.objects.filter(
            tenant=self.context["tenant"], user__email__iexact=email
        ).exists():
            raise serializers.ValidationError("This person is already a member of this business.")
        if Invitation.objects.filter(
            tenant=self.context["tenant"],
            email__iexact=email,
            expires_at__gt=timezone.now(),
        ).exists():
            raise serializers.ValidationError(
                "This email already has a pending invitation to this business."
            )
        return email


class InvitationLookupSerializer(serializers.Serializer):
    """Serializer for reading an invitation from the token in its link."""

    token = serializers.CharField()
    lock_invitation = False

    def validate(self, attrs):
        invitations = Invitation.objects.filter(
            token=attrs["token"],
            expires_at__gt=timezone.now(),
            tenant__is_deleted=False,
        )
        if self.lock_invitation:
            invitations = invitations.select_for_update(of=("self",))
        invitation = invitations.first()
        user = invitation and User.objects.filter(email__iexact=invitation.email).first()
        if invitation is None or (user is not None and not user.is_active):
            raise serializers.ValidationError(
                {"token": ["The invitation is invalid or has expired."]}
            )
        attrs["invitation"] = invitation
        attrs["user"] = user
        return attrs


class InvitationAcceptSerializer(InvitationLookupSerializer):
    """Serializer for accepting an invitation; validate it inside a transaction."""

    lock_invitation = True

    # Which of these are needed depends on the account, so validate() checks them
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    new_password = serializers.CharField(
        required=False, allow_blank=True, style={"input_type": "password"}
    )
    new_password_confirm = serializers.CharField(
        required=False, allow_blank=True, style={"input_type": "password"}
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        invitation = attrs["invitation"]
        email = invitation.email
        user = attrs["user"]
        request_user = self.context["request"].user
        if request_user.is_authenticated and request_user.email.lower() != email.lower():
            raise PermissionDenied("This invitation was sent to another email.")
        has_password = user is not None and user.has_usable_password()
        if has_password and not request_user.is_authenticated:
            raise NotAuthenticated
        if (
            user is not None
            and Membership.objects.filter(tenant=invitation.tenant, user=user).exists()
        ):
            raise serializers.ValidationError(
                {"token": ["You are already a member of this business."]}
            )
        if has_password:
            return attrs
        required = ("new_password",) if user else ("first_name", "last_name", "new_password")
        missing = {field: ["This field is required."] for field in required if not attrs.get(field)}
        if missing:
            raise serializers.ValidationError(missing)
        if attrs["new_password"] != attrs.get("new_password_confirm"):
            raise serializers.ValidationError({"new_password_confirm": ["Passwords do not match."]})
        candidate = user or User(
            email=email, first_name=attrs["first_name"], last_name=attrs["last_name"]
        )
        try:
            validate_password(attrs["new_password"], candidate)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"new_password": list(error.messages)}) from error
        return attrs
