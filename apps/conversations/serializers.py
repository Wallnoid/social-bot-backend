"""
What the inbox returns: a stable shape for the frontend, without the internal ids or
the 0.3 duplicate names that `wanps.inbox` also includes.
"""

from rest_framework import serializers
from wanps.messaging.attachments import PAGE_FILE_KINDS, WHATSAPP_FILE_KINDS
from wanps.messaging.models import Message

from apps.channels.serializers import CHANNEL_CHOICES

FILE_KINDS = list(dict.fromkeys([*WHATSAPP_FILE_KINDS, *PAGE_FILE_KINDS.values()]))


class ConversationsQuerySerializer(serializers.Serializer):
    """Which chats to return: all the business's accounts on the channel, or only one."""

    account = serializers.UUIDField(
        required=False,
        help_text="Only this account of the business (the id the list of accounts shows).",
    )
    limit = serializers.IntegerField(min_value=1, max_value=100, default=50)
    offset = serializers.IntegerField(min_value=0, default=0)


class MessagesQuerySerializer(serializers.Serializer):
    """Which chat's messages: the account is always needed, because one client can write to
    several accounts of the business."""

    account = serializers.UUIDField()
    limit = serializers.IntegerField(min_value=1, max_value=100, default=50)
    before = serializers.IntegerField(min_value=1, required=False)


class FileQuerySerializer(serializers.Serializer):
    """Which account the chat of the file belongs to (the same account the messages need)."""

    account = serializers.UUIDField()


class InboxAccountSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    channel = serializers.ChoiceField(choices=CHANNEL_CHOICES)


class MessageFileSerializer(serializers.Serializer):
    """The file a message carries. The type and the name are empty when Meta does not send them."""

    kind = serializers.ChoiceField(choices=FILE_KINDS)
    mime_type = serializers.CharField()
    filename = serializers.CharField()


class InboxMessageSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    direction = serializers.ChoiceField(
        choices=[Message.DIRECTION_IN, Message.DIRECTION_OUT],
        help_text="in: the client wrote it. out: the business sent it, a person or the bot.",
    )
    type = serializers.CharField(
        help_text="What the message is: text, image, audio, video, document, sticker, location, "
        "contacts, button, interactive or template. Meta may send other values, so do not treat "
        "this as a closed list."
    )
    text = serializers.CharField(
        help_text="The text, or the caption of a file. A message with a file and no caption "
        "carries a marker such as [image] or [sticker]: show the file (see `file`), not the marker."
    )
    status = serializers.CharField(
        help_text="Delivery of a message the business sent: sent, delivered, read or failed. "
        "Empty for incoming messages. Meta may send other values, so do not treat this as a "
        "closed list."
    )
    sent_by = serializers.CharField(
        help_text="Full name of the person who sent it by hand. Empty for the bot and for "
        "incoming messages."
    )
    created_at = serializers.DateTimeField()


class ChatMessageSerializer(InboxMessageSerializer):
    """A message as the chat shows it: the list of chats keeps its smaller `last_message`."""

    file = MessageFileSerializer(allow_null=True, help_text="The file the message carries, if any.")


class ConversationSerializer(serializers.Serializer):
    account = InboxAccountSerializer()
    channel = serializers.ChoiceField(choices=CHANNEL_CHOICES)
    contact_id = serializers.CharField()
    contact_name = serializers.CharField(
        help_text="The name of the client. While Meta has not given it, Messenger shows "
        "'Messenger user' and Instagram 'Instagram user'; WhatsApp sends it with each message."
    )
    last_message = InboxMessageSerializer()
    window_open = serializers.BooleanField()
    bot_paused = serializers.BooleanField()
    bot_paused_until = serializers.DateTimeField(allow_null=True)
    paused_by = serializers.CharField()
    bot_blocked_until = serializers.DateTimeField(
        allow_null=True,
        help_text="Until when the bot does not answer this client because they insisted on messages "
        "unrelated to the business. Empty when they are not blocked.",
    )


class ChatMessagesSerializer(serializers.Serializer):
    account = InboxAccountSerializer()
    channel = serializers.ChoiceField(choices=CHANNEL_CHOICES)
    contact_id = serializers.CharField()
    window_open = serializers.BooleanField()
    bot_paused = serializers.BooleanField()
    bot_paused_until = serializers.DateTimeField(allow_null=True)
    paused_by = serializers.CharField()
    bot_blocked_until = serializers.DateTimeField(
        allow_null=True,
        help_text="Until when the bot does not answer this client because they insisted on messages "
        "unrelated to the business. Empty when they are not blocked.",
    )
    messages = ChatMessageSerializer(many=True)
    has_more = serializers.BooleanField()


class TemplateToSendSerializer(serializers.Serializer):
    """An approved WhatsApp template and the values to fill in, in order."""

    name = serializers.CharField()
    language = serializers.CharField()
    params = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class SendMessageSerializer(serializers.Serializer):
    """A reply typed by a person: the account of the chat and the text, or a template."""

    account = serializers.UUIDField()
    text = serializers.CharField(required=False)
    template = TemplateToSendSerializer(
        required=False,
        help_text="WhatsApp only, instead of the text. It can go out of the 24-hour window.",
    )
    human_agent = serializers.BooleanField(
        default=False,
        help_text="Messenger and Instagram only: reply as a person once the 24-hour window is "
        "closed, up to 7 days after the client's last message. While the window is open it has "
        "no effect.",
    )

    def validate(self, attrs):
        if bool(attrs.get("text")) == bool(attrs.get("template")):
            raise serializers.ValidationError(
                "Send either 'text' or 'template', not both and not neither."
            )
        return attrs


class PauseBotSerializer(serializers.Serializer):
    """Pause the bot in a chat (for some minutes or until resumed) or resume it."""

    account = serializers.UUIDField()
    paused = serializers.BooleanField()
    minutes = serializers.IntegerField(min_value=1, max_value=10080, required=False)


class UnblockSerializer(serializers.Serializer):
    """The account of the chat whose client is blocked (the one the messages need too)."""

    account = serializers.UUIDField()


class BotStateSerializer(serializers.Serializer):
    account = InboxAccountSerializer()
    channel = serializers.ChoiceField(choices=CHANNEL_CHOICES)
    contact_id = serializers.CharField()
    bot_paused = serializers.BooleanField()
    bot_paused_until = serializers.DateTimeField(allow_null=True)
    paused_by = serializers.CharField()


class TemplatesQuerySerializer(serializers.Serializer):
    """Whose templates: an account of the business."""

    account = serializers.UUIDField()


class TemplateSerializer(serializers.Serializer):
    """An approved template that can be sent from here."""

    name = serializers.CharField()
    language = serializers.CharField()
    category = serializers.CharField()
    body = serializers.CharField(help_text="The text, with its {{1}}, {{2}}... placeholders.")
    variables = serializers.IntegerField(help_text="How many values the template takes.")
