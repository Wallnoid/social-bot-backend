from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from wanps.inbox.services import serialize_message
from wanps.messaging.models import Message

from apps.channels.serializers import CHANNEL_CHOICES
from apps.conversations.names import account_of, display_name
from apps.conversations.serializers import InboxAccountSerializer, InboxMessageSerializer

from .models import Contact, Stage


class ContactStageSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)


class StageSerializer(ContactStageSerializer):
    contacts = serializers.IntegerField(
        source="contact_count", read_only=True, help_text="How many contacts it has."
    )


class ContactSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.SerializerMethodField(
        help_text="The name to show: the one the team wrote (`custom_name`), else the one the "
        "channel gave. While Meta has not given it, Messenger shows 'Messenger user' and "
        "Instagram 'Instagram user'; on WhatsApp it stays empty (show `contact_id`, the phone)."
    )
    custom_name = serializers.CharField(
        source="name",
        read_only=True,
        help_text="The name the team wrote, empty if none: fill the edit form with this one.",
    )
    contact_id = serializers.CharField(
        source="external_id",
        read_only=True,
        help_text="The client on the channel: the phone on WhatsApp, the user id elsewhere.",
    )
    channel = serializers.ChoiceField(
        choices=CHANNEL_CHOICES, source="account.channel", read_only=True
    )
    stage = ContactStageSerializer(read_only=True, help_text="The stage of the pipeline.")
    phone = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    company = serializers.CharField(read_only=True)
    last_contact_at = serializers.DateTimeField(
        read_only=True,
        help_text="When the latest message of the chat, from either side, was saved.",
    )

    @extend_schema_field(serializers.CharField())
    def get_name(self, contact):
        # The name the team wrote, else the one the channel gives (shown, never saved)
        return display_name(contact.account.channel, contact.name or contact.channel_name)


class StageOfBusinessField(serializers.PrimaryKeyRelatedField):
    """A stage of the active business: one of another business is as one that does not exist."""

    def get_queryset(self):
        return Stage.objects.filter(tenant=self.context["request"].tenant)


class ContactEditSerializer(serializers.ModelSerializer):
    stage = StageOfBusinessField(required=False, help_text="Moves the contact to this stage.")
    # Free text, not E.164: digits, "+", spaces and dashes, with at least one digit
    phone = serializers.RegexField(
        r"^([0-9+\- ]*[0-9][0-9+\- ]*)?$", max_length=32, required=False, allow_blank=True
    )

    class Meta:
        model = Contact
        fields = ["name", "phone", "email", "company", "stage"]

    def validate_email(self, email):
        # Stored in lowercase, as the emails of users
        return email.lower()

    def update(self, contact, validated_data):
        # Only the fields sent: the contact read with the file carries annotations
        for field, value in validated_data.items():
            setattr(contact, field, value)
        contact.save(update_fields=[*validated_data, "updated_at"])
        return contact


class ContactConversationSerializer(serializers.Serializer):
    account = InboxAccountSerializer()
    channel = serializers.ChoiceField(choices=CHANNEL_CHOICES)
    contact_id = serializers.CharField(help_text="With `account`, opens the chat in the inbox.")
    connected = serializers.BooleanField(
        help_text="False when the account was disconnected: the chat cannot be opened."
    )
    last_message = InboxMessageSerializer(allow_null=True)


class ContactFileSerializer(ContactSerializer):
    account = serializers.SerializerMethodField(
        help_text="The channel account of the business the contact writes to."
    )
    first_contact_at = serializers.DateTimeField(
        read_only=True, help_text="When the first message of the chat was saved."
    )
    conversations = serializers.SerializerMethodField(
        help_text="The chats of the contact (one for now). Their messages are read in the inbox."
    )

    @extend_schema_field(InboxAccountSerializer())
    def get_account(self, contact):
        # As the inbox gives it: the id of the link to the business opens the chat
        return InboxAccountSerializer(account_of(contact.account.channel_account)).data

    @extend_schema_field(ContactConversationSerializer(many=True))
    def get_conversations(self, contact):
        last = (
            # The chat the inbox opens: the account, its channel and the client
            Message.objects.filter(
                account_id=contact.account_id,
                channel=contact.account.channel,
                contact_id=contact.external_id,
            )
            .order_by("-id")
            .first()
        )
        conversation = {
            "account": self.get_account(contact),
            "channel": contact.account.channel,
            "contact_id": contact.external_id,
            "connected": not contact.account.channel_account.is_deleted,
            "last_message": serialize_message(last) if last else None,
        }
        return ContactConversationSerializer([conversation], many=True).data


class ContactsQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(min_value=1, max_value=100, default=50)
    offset = serializers.IntegerField(min_value=0, default=0)
    stage = serializers.UUIDField(
        required=False, help_text="Only the contacts of this stage: a column of the pipeline."
    )
