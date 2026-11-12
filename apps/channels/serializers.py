"""
Serializers for the channels app.
"""

from django.conf import settings
from django.urls import reverse
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator
from wanps.messaging.models import Account, App

from .models import ChannelAccount

ALREADY_CONNECTED = "This account is already connected."

# The wanps-core channels this backend installs (one list, so the API docs name it once)
CHANNEL_CHOICES = ["whatsapp", "messenger", "instagram"]


class ConnectAccountSerializer(serializers.ModelSerializer):
    """Data a business admin types to connect a number, page or Instagram account."""

    channel = serializers.ChoiceField(choices=CHANNEL_CHOICES)

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


def ai_is_available(account):
    """
    Whether the bot of this account would have an AI to answer with: its own, or the one of the
    platform. It mirrors how wanps-core chooses: another provider than the platform's never
    borrows the platform's key.
    """
    platform = dict(getattr(settings, "WANPS_AI", None) or {})
    provider = account.ai_provider or platform.get("PROVIDER")
    if not provider:
        return False
    same_as_platform = str(provider).lower() == str(platform.get("PROVIDER") or "").lower()
    return bool(account.ai_api_key or (platform.get("API_KEY") if same_as_platform else None))


class UpdateAccountSerializer(serializers.ModelSerializer):
    """What a business admin can change on a connected account."""

    instructions = serializers.CharField(
        source="system_prompt",
        required=False,
        allow_blank=True,
        help_text="How the bot must behave and what it must know about the business.",
    )

    class Meta:
        model = Account
        fields = ["name", "access_token", "is_active", "instructions"]
        # Like when connecting: the token goes in encrypted and never comes back out
        extra_kwargs = {
            "access_token": {"write_only": True, "allow_blank": False},
            "is_active": {"help_text": "Whether the bot answers the clients of this account."},
        }

    def validate(self, attrs):
        if "is_active" not in attrs and "system_prompt" not in attrs:
            return attrs  # a rename or a new token never depends on the bot
        is_on = attrs.get("is_active", self.instance.is_active)
        instructions = attrs.get("system_prompt", self.instance.system_prompt)
        if is_on and not instructions.strip():
            raise serializers.ValidationError(
                {
                    "instructions": "Write the instructions of the bot first: "
                    "without them it would answer your clients with no guidance."
                }
            )
        if attrs.get("is_active") and not ai_is_available(self.instance):
            raise serializers.ValidationError(
                {
                    "is_active": "The bot cannot be turned on right now because no AI is set up. "
                    "Ask the Social Bot team."
                }
            )
        return attrs

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        # Only the edited columns: wanps-core may be changing the rest of the account right now
        instance.save(update_fields=[*validated_data, "updated_at"])
        return instance


class ChannelAccountSerializer(serializers.ModelSerializer):
    """A connected account as the business sees it: never its token."""

    channel = serializers.ChoiceField(
        choices=CHANNEL_CHOICES, source="account.channel", read_only=True
    )
    name = serializers.CharField(source="account.name", read_only=True)
    external_id = serializers.CharField(source="account.external_id", read_only=True)
    business_id = serializers.CharField(source="account.business_id", read_only=True)
    is_active = serializers.BooleanField(
        source="account.is_active", read_only=True, help_text="Whether the bot answers the clients."
    )
    instructions = serializers.CharField(
        source="account.system_prompt",
        read_only=True,
        help_text="How the bot must behave and what it must know about the business.",
    )

    class Meta:
        model = ChannelAccount
        fields = [
            "id",
            "channel",
            "name",
            "external_id",
            "business_id",
            "is_active",
            "instructions",
        ]


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
