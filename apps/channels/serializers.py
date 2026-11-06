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
        # The token goes in and is stored encrypted by wanps-core; it never comes back out.
        # wanps-core lets it be empty, but an account without a token cannot send anything
        extra_kwargs = {
            "access_token": {"write_only": True, "required": True, "allow_blank": False}
        }
        # Same answer whoever owns it, so it never tells which business has the account
        validators = [
            UniqueTogetherValidator(
                queryset=Account.objects.all(),
                fields=["channel", "external_id"],
                message=ALREADY_CONNECTED,
            )
        ]


class UpdateAccountSerializer(serializers.ModelSerializer):
    """What a business admin can change on a connected account."""

    class Meta:
        model = Account
        fields = ["name", "access_token"]
        # Like when connecting: the token goes in encrypted and never comes back out
        extra_kwargs = {"access_token": {"write_only": True, "allow_blank": False}}

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        # Only the edited columns: wanps-core may be changing the rest of the account right now
        instance.save(update_fields=[*validated_data, "updated_at"])
        return instance


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
