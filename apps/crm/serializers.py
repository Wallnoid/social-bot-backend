from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.conversations.names import display_name


class ContactSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.SerializerMethodField(
        help_text="The name the channel gave for the client. While Meta has not given it, "
        "Messenger shows 'Messenger user' and Instagram 'Instagram user'; on WhatsApp it stays "
        "empty (show `contact_id`, the phone)."
    )
    contact_id = serializers.CharField(
        source="external_id",
        read_only=True,
        help_text="The client on the channel: the phone on WhatsApp, the user id elsewhere.",
    )
    channel = serializers.CharField(source="account.channel", read_only=True)
    last_contact_at = serializers.DateTimeField(
        read_only=True,
        help_text="When the latest message of the chat, from either side, was saved.",
    )

    @extend_schema_field(serializers.CharField())
    def get_name(self, contact):
        # Shown, never saved: the same name the inbox shows
        return display_name(contact.account.channel, contact.name)


class ContactsQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(min_value=1, max_value=100, default=50)
    offset = serializers.IntegerField(min_value=0, default=0)
