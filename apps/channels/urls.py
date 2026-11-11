"""
URL configuration for the channels app.
"""

from django.urls import path

from .views import ChannelAccountDetailView, ChannelAccountListView, MetaAppView

app_name = "channels"

urlpatterns = [
    path("meta-app/", MetaAppView.as_view(), name="meta-app"),
    path("accounts/", ChannelAccountListView.as_view(), name="account-list"),
    path("accounts/<uuid:account_id>/", ChannelAccountDetailView.as_view(), name="account-detail"),
]
