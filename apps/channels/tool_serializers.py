"""
Serializers of the tools of a bot: what a business admin sends and sees. The key of the endpoint
goes in and never comes out.
"""

import re
from urllib.parse import urlsplit

from rest_framework import serializers

from .models import ChannelTool

MAX_TOOLS_PER_ACCOUNT = 10
# What the AI providers accept as the name of a function
NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
HEADER_NAME = re.compile(r"[A-Za-z][A-Za-z0-9-]{0,63}")
# Headers that the call itself sets: a tool must not override them
FORBIDDEN_HEADERS = {"host", "content-length", "transfer-encoding", "connection"}
PARAMETER_TYPES = ["string", "number", "boolean"]
# Names that wanps-core fills in by itself, so the AI never gives them
RESERVED_PARAMETERS = {"account", "msg"}


def valid_name(value):
    if not NAME.fullmatch(value):
        raise serializers.ValidationError(
            "Use lowercase letters, digits and underscores, starting with a letter (up to 64)."
        )
    return value


def valid_parameter_name(value):
    valid_name(value)
    if value in RESERVED_PARAMETERS:
        raise serializers.ValidationError("The system fills in this name by itself: use another.")
    return value


class StrictBooleanField(serializers.BooleanField):
    """Only true or false: DRF's default also takes "yes", "on", "1"..."""

    TRUE_VALUES = {True}
    FALSE_VALUES = {False}


class ToolParameterSerializer(serializers.Serializer):
    """One value the AI gives when it asks for the tool: it goes in the query of the address."""

    name = serializers.CharField(validators=[valid_parameter_name])
    type = serializers.ChoiceField(choices=PARAMETER_TYPES)
    description = serializers.CharField(allow_blank=True, max_length=500, default="")
    required = StrictBooleanField(default=False)


class ChannelToolSerializer(serializers.ModelSerializer):
    """A tool of the bot of an account. Everything but the key is shown back."""

    name = serializers.CharField(validators=[valid_name])
    description = serializers.CharField(max_length=2000)
    url = serializers.CharField(
        max_length=500, help_text="An https address. The values of the parameters go in its query."
    )
    parameters = ToolParameterSerializer(many=True, required=False)
    auth_type = serializers.ChoiceField(
        choices=ChannelTool.AuthType.choices,
        default=ChannelTool.AuthType.NONE,
        help_text="none, a Bearer token, or a key in the header named by auth_header. "
        "Changing the type clears the key and the header unless new ones are sent.",
    )
    auth_header = serializers.CharField(required=False, allow_blank=True, max_length=64)
    auth_secret = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="The token or key. It is stored encrypted and never returned.",
    )
    has_secret = serializers.SerializerMethodField()

    class Meta:
        model = ChannelTool
        fields = [
            "id",
            "name",
            "description",
            "url",
            "parameters",
            "auth_type",
            "auth_header",
            "auth_secret",
            "has_secret",
            "is_active",
        ]

    def get_has_secret(self, tool) -> bool:
        return bool(tool.auth_secret)

    def validate_name(self, value):
        taken = ChannelTool.objects.filter(account=self.context["account"], name=value)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError("This account already has a tool with that name.")
        return value

    def validate_auth_secret(self, value):
        # It travels in a header: only characters every HTTP library can send
        if value and not (value.isascii() and value.isprintable()):
            raise serializers.ValidationError(
                "Use only printable ASCII characters: no accents, smart quotes or line breaks."
            )
        return value

    def validate_url(self, value):
        try:
            parts = urlsplit(value)
            parts.port  # noqa: B018  (a bad port raises here)
        except ValueError:
            raise serializers.ValidationError("This is not a valid address.") from None
        if parts.scheme != "https" or not parts.hostname:
            raise serializers.ValidationError("Use an https address.")
        if parts.username or parts.password:
            raise serializers.ValidationError("The address cannot carry a user or a password.")
        return value

    def validate_parameters(self, value):
        names = [parameter["name"] for parameter in value]
        if len(names) != len(set(names)):
            raise serializers.ValidationError("Two parameters cannot have the same name.")
        return [dict(parameter) for parameter in value]

    def validate(self, attrs):
        changes_type = (
            self.instance is not None
            and "auth_type" in attrs
            and attrs["auth_type"] != self.instance.auth_type
        )
        if changes_type:
            # What the old type used does not carry over to the new one
            attrs.setdefault("auth_header", "")
            attrs.setdefault("auth_secret", "")

        def current(field, default):
            return attrs.get(field, getattr(self.instance, field, default))

        auth_type = current("auth_type", ChannelTool.AuthType.NONE)
        header, secret = current("auth_header", ""), current("auth_secret", "")
        errors = {}
        if auth_type == ChannelTool.AuthType.NONE:
            if secret:
                errors["auth_secret"] = "A tool without authentication has no key."
            if header:
                errors["auth_header"] = "A tool without authentication has no header."
        else:
            if not secret:
                errors["auth_secret"] = "This field is required."
            if auth_type == ChannelTool.AuthType.HEADER and (
                not HEADER_NAME.fullmatch(header) or header.lower() in FORBIDDEN_HEADERS
            ):
                errors["auth_header"] = "Give a valid name for the header that carries the key."
            if auth_type == ChannelTool.AuthType.BEARER and header:
                errors["auth_header"] = "A Bearer token has no header name."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs
