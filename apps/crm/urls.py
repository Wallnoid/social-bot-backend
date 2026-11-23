"""
URL configuration for the crm app.
"""

from django.urls import path

from .views import (
    ContactDetailView,
    ContactListView,
    StageDetailView,
    StageListView,
    StageOrderView,
)

app_name = "crm"

urlpatterns = [
    path("contacts/", ContactListView.as_view(), name="contact-list"),
    path("contacts/<uuid:contact_id>/", ContactDetailView.as_view(), name="contact-detail"),
    path("stages/", StageListView.as_view(), name="stage-list"),
    path("stages/order/", StageOrderView.as_view(), name="stage-order"),
    path("stages/<uuid:stage_id>/", StageDetailView.as_view(), name="stage-detail"),
]
