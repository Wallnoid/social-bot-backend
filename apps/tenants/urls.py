"""
URL configuration for the tenants app.
"""

from django.urls import path

from .views import CurrentTenantView

app_name = "tenants"

urlpatterns = [
    path("current/", CurrentTenantView.as_view(), name="current"),
]
