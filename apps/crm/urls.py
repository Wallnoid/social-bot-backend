"""
URL configuration for the crm app.
"""

from django.urls import path

from .views import ContactListView

app_name = "crm"

urlpatterns = [
    path("contacts/", ContactListView.as_view(), name="contact-list"),
]
