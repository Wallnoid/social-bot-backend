"""
What the inbox returns: a stable shape for the frontend, without the internal ids or
the 0.3 duplicate names that `wanps.inbox` also includes.
"""

from rest_framework import serializers


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


class InboxAccountSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    channel = serializers.CharField()


class InboxMessageSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    direction = serializers.CharField()
    type = serializers.CharField()
    text = serializers.CharField()
    status = serializers.CharField()
    sent_by = serializers.CharField()
    created_at = serializers.DateTimeField()


class ConversationSerializer(serializers.Serializer):
    account = InboxAccountSerializer()
    channel = serializers.CharField()
    contact_id = serializers.CharField()
    contact_name = serializers.CharField()
    last_message = InboxMessageSerializer()
    window_open = serializers.BooleanField()
    bot_paused = serializers.BooleanField()
    bot_paused_until = serializers.DateTimeField(allow_null=True)
    paused_by = serializers.CharField()


class ChatMessagesSerializer(serializers.Serializer):
    account = InboxAccountSerializer()
    channel = serializers.CharField()
    contact_id = serializers.CharField()
    window_open = serializers.BooleanField()
    bot_paused = serializers.BooleanField()
    bot_paused_until = serializers.DateTimeField(allow_null=True)
    paused_by = serializers.CharField()
    messages = InboxMessageSerializer(many=True)
    has_more = serializers.BooleanField()


class SendMessageSerializer(serializers.Serializer):
    """A reply typed by a person: the account of the chat and the text."""

    account = serializers.UUIDField()
    text = serializers.CharField()


class PauseBotSerializer(serializers.Serializer):
    """Pause the bot in a chat (for some minutes or until resumed) or resume it."""

    account = serializers.UUIDField()
    paused = serializers.BooleanField()
    minutes = serializers.IntegerField(min_value=1, max_value=10080, required=False)


class BotStateSerializer(serializers.Serializer):
    account = InboxAccountSerializer()
    channel = serializers.CharField()
    contact_id = serializers.CharField()
    bot_paused = serializers.BooleanField()
    bot_paused_until = serializers.DateTimeField(allow_null=True)
    paused_by = serializers.CharField()
