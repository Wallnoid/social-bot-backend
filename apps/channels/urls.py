"""
URL configuration for the channels app.
"""

from django.urls import path

from .views import ChannelAccountListView

app_name = "channels"

urlpatterns = [
    path("accounts/", ChannelAccountListView.as_view(), name="account-list"),
]
