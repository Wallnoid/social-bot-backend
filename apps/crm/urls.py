"""
URL configuration for the crm app.
"""

from django.urls import path

from .views import (
    ContactDetailView,
    ContactListView,
    ContactMergeView,
    ContactTagDetailView,
    ContactTagListView,
    NoteDetailView,
    NoteListView,
    StageDetailView,
    StageListView,
    StageOrderView,
    TagListView,
)

app_name = "crm"

urlpatterns = [
    path("contacts/", ContactListView.as_view(), name="contact-list"),
    path("contacts/<uuid:contact_id>/", ContactDetailView.as_view(), name="contact-detail"),
    path("contacts/<uuid:contact_id>/merge/", ContactMergeView.as_view(), name="contact-merge"),
    path("contacts/<uuid:contact_id>/notes/", NoteListView.as_view(), name="note-list"),
    path(
        "contacts/<uuid:contact_id>/notes/<uuid:note_id>/",
        NoteDetailView.as_view(),
        name="note-detail",
    ),
    path("contacts/<uuid:contact_id>/tags/", ContactTagListView.as_view(), name="contact-tags"),
    path(
        "contacts/<uuid:contact_id>/tags/<uuid:tag_id>/",
        ContactTagDetailView.as_view(),
        name="contact-tag-detail",
    ),
    path("tags/", TagListView.as_view(), name="tag-list"),
    path("stages/", StageListView.as_view(), name="stage-list"),
    path("stages/order/", StageOrderView.as_view(), name="stage-order"),
    path("stages/<uuid:stage_id>/", StageDetailView.as_view(), name="stage-detail"),
]
