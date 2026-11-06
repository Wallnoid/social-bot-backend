"""
URL configuration for the inbox: one inbox per channel.
"""

from django.urls import re_path

from .views import ConversationListView, MessageListView

app_name = "conversations"

# Only the channels this backend installs; any other answers 404
CHANNEL = r"(?P<channel>whatsapp|messenger|instagram)"

urlpatterns = [
    re_path(
        rf"^{CHANNEL}/conversations/$", ConversationListView.as_view(), name="conversation-list"
    ),
    re_path(
        rf"^{CHANNEL}/conversations/(?P<contact_id>[^/]+)/messages/$",
        MessageListView.as_view(),
        name="message-list",
    ),
]
