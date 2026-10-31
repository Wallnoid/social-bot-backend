"""
URL configuration for the tenants app.
"""

from django.urls import path

from .views import (
    CurrentTenantView,
    InvitationAcceptView,
    InvitationCreateView,
    InvitationLookupView,
)

app_name = "tenants"

urlpatterns = [
    path("current/", CurrentTenantView.as_view(), name="current"),
    path("invitations/", InvitationCreateView.as_view(), name="invitations"),
    path("invitations/lookup/", InvitationLookupView.as_view(), name="invitation-lookup"),
    path("invitations/accept/", InvitationAcceptView.as_view(), name="invitation-accept"),
]
