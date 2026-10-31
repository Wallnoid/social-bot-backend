"""
URL configuration for the tenants app.
"""

from django.urls import path

from .views import (
    CurrentTenantView,
    InvitationAcceptView,
    InvitationCreateView,
    InvitationLookupView,
    MemberDetailView,
    MemberListView,
)

app_name = "tenants"

urlpatterns = [
    path("current/", CurrentTenantView.as_view(), name="current"),
    path("invitations/", InvitationCreateView.as_view(), name="invitations"),
    path("invitations/lookup/", InvitationLookupView.as_view(), name="invitation-lookup"),
    path("invitations/accept/", InvitationAcceptView.as_view(), name="invitation-accept"),
    path("members/", MemberListView.as_view(), name="members"),
    path("members/<uuid:member_id>/", MemberDetailView.as_view(), name="member-detail"),
]
