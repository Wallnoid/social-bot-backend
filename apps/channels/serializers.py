"""
Serializers for the channels app.
"""

from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator
from wanps.messaging.models import Account

from .models import ChannelAccount

ALREADY_CONNECTED = "This account is already connected."


class ConnectAccountSerializer(serializers.ModelSerializer):
    """Data a business admin types to connect a number, page or Instagram account."""

    # The wanps-core channels this backend installs
    channel = serializers.ChoiceField(choices=["whatsapp", "messenger", "instagram"])

    class Meta:
        model = Account
        fields = ["channel", "name", "external_id", "business_id", "access_token"]
        # The token goes in and is stored encrypted by wanps-core; it never comes back out
        extra_kwargs = {"access_token": {"write_only": True}}
        # Same answer whoever owns it, so it never tells which business has the account
        validators = [
            UniqueTogetherValidator(
                queryset=Account.objects.all(),
                fields=["channel", "external_id"],
                message=ALREADY_CONNECTED,
            )
        ]


class ChannelAccountSerializer(serializers.ModelSerializer):
    """A connected account as the business sees it: never its token."""

    channel = serializers.CharField(source="account.channel", read_only=True)
    name = serializers.CharField(source="account.name", read_only=True)
    external_id = serializers.CharField(source="account.external_id", read_only=True)
    business_id = serializers.CharField(source="account.business_id", read_only=True)
    is_active = serializers.BooleanField(source="account.is_active", read_only=True)

    class Meta:
        model = ChannelAccount
        fields = ["id", "channel", "name", "external_id", "business_id", "is_active"]
