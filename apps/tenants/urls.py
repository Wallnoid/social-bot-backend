"""
URL configuration for the tenants app.
"""

from django.urls import path

from .views import CurrentTenantView, InvitationCreateView

app_name = "tenants"

urlpatterns = [
    path("current/", CurrentTenantView.as_view(), name="current"),
    path("invitations/", InvitationCreateView.as_view(), name="invitations"),
]
