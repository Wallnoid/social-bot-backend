"""
URL configuration for the channels app.
"""

from django.urls import path

from .tool_views import ChannelToolDetailView, ChannelToolListView
from .views import ChannelAccountDetailView, ChannelAccountListView, MetaAppView

app_name = "channels"

urlpatterns = [
    path("meta-app/", MetaAppView.as_view(), name="meta-app"),
    path("accounts/", ChannelAccountListView.as_view(), name="account-list"),
    path("accounts/<uuid:account_id>/", ChannelAccountDetailView.as_view(), name="account-detail"),
    path("accounts/<uuid:account_id>/tools/", ChannelToolListView.as_view(), name="tool-list"),
    path(
        "accounts/<uuid:account_id>/tools/<uuid:tool_id>/",
        ChannelToolDetailView.as_view(),
        name="tool-detail",
    ),
]
