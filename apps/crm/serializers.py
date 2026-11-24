from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from wanps.inbox.services import serialize_message
from wanps.messaging.models import Message

from apps.channels.serializers import CHANNEL_CHOICES
from apps.conversations.names import account_of, display_name
from apps.conversations.serializers import InboxAccountSerializer, InboxMessageSerializer
from apps.tenants.models import Membership

from .models import Contact, Note, Stage, Tag, stage_was_deleted


class ContactStageSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)


class TagSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)


class TagCountSerializer(TagSerializer):
    contacts = serializers.IntegerField(
        source="contact_count", read_only=True, help_text="How many contacts have it."
    )


class TagNameSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=Tag._meta.get_field("name").max_length)


class StageSerializer(ContactStageSerializer):
    contacts = serializers.IntegerField(
        source="contact_count", read_only=True, help_text="How many contacts it has."
    )


class StageNameSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)

    def validate_name(self, name):
        # Two columns of the board with the same name cannot be told apart
        others = Stage.objects.filter(tenant=self.context["request"].tenant, name__iexact=name)
        if self.instance is not None:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise serializers.ValidationError("The business already has a stage with this name.")
        return name


class StageOrderSerializer(serializers.Serializer):
    stages = serializers.ListField(
        child=serializers.UUIDField(), help_text="Every stage of the business, in the new order."
    )


class StageDeleteQuerySerializer(serializers.Serializer):
    move_to = serializers.UUIDField(
        required=False,
        help_text="The stage its contacts move to; required when the stage has contacts.",
    )


class PersonInChargeSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True, help_text="The id of the member of the business.")
    name = serializers.CharField(source="user.full_name", read_only=True)


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
    tags = TagSerializer(many=True, read_only=True, help_text="The tags of the contact, by name.")
    assigned_to = serializers.SerializerMethodField(
        help_text="The member in charge of the contact, empty if nobody."
    )
    phone = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    company = serializers.CharField(read_only=True)
    last_contact_at = serializers.DateTimeField(
        read_only=True,
        help_text="When the latest message of the chat, from either side, was saved.",
    )

    @extend_schema_field(PersonInChargeSerializer(allow_null=True))
    def get_assigned_to(self, contact):
        member = contact.assigned_to
        # A member who left the business is no longer in charge
        if member is None or member.is_deleted:
            return None
        return PersonInChargeSerializer(member).data

    @extend_schema_field(serializers.CharField())
    def get_name(self, contact):
        # The name the team wrote, else the one the channel gives (shown, never saved)
        return display_name(contact.account.channel, contact.name or contact.channel_name)


@extend_schema_field(serializers.UUIDField())
class ContactOfBusinessField(serializers.PrimaryKeyRelatedField):
    """A contact of the active business: one of another business is as one that does not exist."""

    def get_queryset(self):
        return Contact.objects.filter(tenant=self.context["request"].tenant)


class ContactMergeSerializer(serializers.Serializer):
    contact = ContactOfBusinessField(
        help_text="The contact that goes into the one of the URL: it is deleted, and its chats, "
        "notes and tags pass to the other."
    )

    def validate_contact(self, value):
        if value.pk == self.context["kept_id"]:
            raise serializers.ValidationError("A contact cannot be merged into itself.")
        return value


class StageOfBusinessField(serializers.PrimaryKeyRelatedField):
    """A stage of the active business: one of another business is as one that does not exist."""

    def get_queryset(self):
        return Stage.objects.filter(tenant=self.context["request"].tenant)


class MemberOfBusinessField(serializers.PrimaryKeyRelatedField):
    """A member of the active business: one of another business is as one that does not exist."""

    def get_queryset(self):
        return Membership.objects.select_related("user").filter(
            tenant=self.context["request"].tenant
        )


class ContactEditSerializer(serializers.ModelSerializer):
    stage = StageOfBusinessField(required=False, help_text="Moves the contact to this stage.")
    assigned_to = MemberOfBusinessField(
        required=False,
        allow_null=True,
        help_text="The member in charge of the contact (`id` in the list of members); empty "
        "takes the person off.",
    )
    # Free text, not E.164: digits, "+", spaces and dashes, with at least one digit
    phone = serializers.RegexField(
        r"^([0-9+\- ]*[0-9][0-9+\- ]*)?$", max_length=32, required=False, allow_blank=True
    )

    class Meta:
        model = Contact
        fields = ["name", "phone", "email", "company", "stage", "assigned_to"]

    def validate_email(self, email):
        # Stored in lowercase, as the emails of users
        return email.lower()

    def update(self, contact, validated_data):
        # Only the fields sent: the contact read with the file carries annotations
        for field, value in validated_data.items():
            setattr(contact, field, value)
        with transaction.atomic():
            contact.save(update_fields=[*validated_data, "updated_at"])
            if "stage" in validated_data and stage_was_deleted(contact.stage_id):
                raise serializers.ValidationError({"stage": ["This stage was just deleted."]})
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
        help_text="The chats of the contact, its own first. Their messages are read in the inbox."
    )

    @extend_schema_field(InboxAccountSerializer())
    def get_account(self, contact):
        # As the inbox gives it: the id of the link to the business opens the chat
        return InboxAccountSerializer(account_of(contact.account.channel_account)).data

    @extend_schema_field(ContactConversationSerializer(many=True))
    def get_conversations(self, contact):
        # Its own chat first, then the ones of the contacts merged into it
        merged = (
            Contact.all_objects.filter(merged_into=contact)
            .select_related("account__channel_account")
            .order_by("created_at", "id")
        )
        conversations = [self.conversation_of(chat) for chat in [contact, *merged]]
        return ContactConversationSerializer(conversations, many=True).data

    def conversation_of(self, chat):
        last = (
            # The chat the inbox opens: the account, its channel and the client
            Message.objects.filter(
                account_id=chat.account_id,
                channel=chat.account.channel,
                contact_id=chat.external_id,
            )
            .order_by("-id")
            .first()
        )
        return {
            "account": self.get_account(chat),
            "channel": chat.account.channel,
            "contact_id": chat.external_id,
            "connected": not chat.account.channel_account.is_deleted,
            "last_message": serialize_message(last) if last else None,
        }


class PageQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(min_value=1, max_value=100, default=50)
    offset = serializers.IntegerField(min_value=0, default=0)


NOBODY = "none"


class ContactsQuerySerializer(PageQuerySerializer):
    """The filters of the contact list; the ones that name something check it is of the business."""

    stage = serializers.UUIDField(
        required=False, help_text="Only the contacts of this stage: a column of the pipeline."
    )
    search = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=100,
        help_text="Part of the name the team wrote or the channel gave, or of the phone, "
        "whatever the capitalization.",
    )
    tag = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="Only the contacts that have every one of these tags (repeat the parameter).",
    )
    assigned_to = serializers.CharField(
        required=False,
        help_text=f"Only the contacts this member is in charge of, or `{NOBODY}` for nobody.",
    )

    def validate_stage(self, value):
        if not Stage.objects.filter(pk=value, tenant=self.context["request"].tenant).exists():
            raise serializers.ValidationError("This stage does not exist.")
        return value

    def validate_tag(self, value):
        wanted = set(value)
        tenant = self.context["request"].tenant
        if Tag.objects.filter(pk__in=wanted, tenant=tenant).count() != len(wanted):
            raise serializers.ValidationError("A tag does not exist.")
        return wanted

    def validate_assigned_to(self, value):
        if value == NOBODY:
            return value
        tenant = self.context["request"].tenant
        try:
            exists = Membership.objects.filter(pk=value, tenant=tenant).exists()
        except (ValueError, DjangoValidationError):
            exists = False
        if not exists:
            raise serializers.ValidationError("This member does not exist.")
        return value


class NoteAuthorSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(source="full_name", read_only=True)


class NoteSerializer(serializers.ModelSerializer):
    author = NoteAuthorSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Note
        fields = ["id", "text", "author", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {"text": {"max_length": 5000}}
