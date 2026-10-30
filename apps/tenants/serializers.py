"""
Serializers for the tenants app.
"""

from django.utils import timezone
from rest_framework import serializers

from .models import Invitation, Membership


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
