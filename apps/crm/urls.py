"""
URL configuration for the crm app.
"""

from django.urls import path

from .views import ContactDetailView, ContactListView, StageListView

app_name = "crm"

urlpatterns = [
    path("contacts/", ContactListView.as_view(), name="contact-list"),
    path("contacts/<uuid:contact_id>/", ContactDetailView.as_view(), name="contact-detail"),
    path("stages/", StageListView.as_view(), name="stage-list"),
]
