"""
Serializers for the channels app.
"""

from django.urls import reverse
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator
from wanps.messaging.models import Account, App

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

    def validate(self, attrs):
        # Meta lists a number's templates under its WhatsApp Business account, so WhatsApp needs it
        if attrs["channel"] == "whatsapp" and not attrs.get("business_id"):
            raise serializers.ValidationError(
                {"business_id": "This field is required for a WhatsApp account."}
            )
        return attrs


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


class MetaAppSerializer(serializers.ModelSerializer):
    """The Meta App of a business: the secret goes in and never comes out."""

    webhook_url = serializers.SerializerMethodField()

    class Meta:
        model = App
        fields = [
            "name",
            "app_id",
            "app_secret",
            "verify_token",
            "api_version",
            "is_active",
            "webhook_url",
        ]
        extra_kwargs = {
            "app_id": {"required": True, "allow_blank": False},
            "app_secret": {"write_only": True, "required": True, "allow_blank": False},
            "verify_token": {"write_only": True, "required": True, "allow_blank": False},
        }

    def validate_app_id(self, value):
        taken = App.objects.filter(app_id=value)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            # Same answer whoever owns it
            raise serializers.ValidationError("This Meta App is already registered.")
        return value

    def get_webhook_url(self, app) -> str:
        path = reverse("messaging:meta-webhook", kwargs={"webhook_key": app.webhook_key})
        return self.context["request"].build_absolute_uri(path)
