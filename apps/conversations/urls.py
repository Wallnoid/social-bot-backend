"""
URL configuration for the inbox: one inbox per channel.
"""

from django.urls import re_path

from .views import (
    BotView,
    ConnectionTicketView,
    ConversationListView,
    MessageFileView,
    MessageListView,
    SendMessageView,
    TemplateListView,
)

app_name = "conversations"

# Only the channels this backend installs; any other answers 404
CHANNEL = r"(?P<channel>whatsapp|messenger|instagram)"

urlpatterns = [
    # The permit to open the permanent connection belongs to the person, not to a channel
    re_path(r"^ws-ticket/$", ConnectionTicketView.as_view(), name="connection-ticket"),
    # The templates belong to the WhatsApp account, not to a chat
    re_path(r"^whatsapp/templates/$", TemplateListView.as_view(), name="template-list"),
    re_path(
        rf"^{CHANNEL}/conversations/$", ConversationListView.as_view(), name="conversation-list"
    ),
    re_path(
        rf"^{CHANNEL}/conversations/(?P<contact_id>[^/]+)/messages/$",
        MessageListView.as_view(),
        name="message-list",
    ),
    re_path(
        rf"^{CHANNEL}/conversations/(?P<contact_id>[^/]+)/messages/(?P<message_id>\d+)/file/$",
        MessageFileView.as_view(),
        name="message-file",
    ),
    re_path(
        rf"^{CHANNEL}/conversations/(?P<contact_id>[^/]+)/send/$",
        SendMessageView.as_view(),
        name="send-message",
    ),
    re_path(
        rf"^{CHANNEL}/conversations/(?P<contact_id>[^/]+)/bot/$",
        BotView.as_view(),
        name="bot",
    ),
]
