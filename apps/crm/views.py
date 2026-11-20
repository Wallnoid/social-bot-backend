"""
Views for the crm app.
"""

from django.db.models import F, OuterRef, Subquery
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from wanps.messaging.models import Message

from apps.tenants.permissions import HasActiveTenant

from .models import Contact
from .serializers import (
    ContactEditSerializer,
    ContactFileSerializer,
    ContactSerializer,
    ContactsQuerySerializer,
)


def chat_of_contact():
    """The messages of the chat of the contact of the outer query: account, channel and client."""
    return Message.objects.filter(
        account_id=OuterRef("account_id"),
        channel=OuterRef("account__channel"),
        contact_id=OuterRef("external_id"),
    )


def contacts_of(tenant):
    """The contacts of a business, with the name and the last contact their chat gives."""
    # The latest message of a chat is the one with the highest id, as the inbox takes it, so
    # both show the same name
    chat = chat_of_contact()
    return (
        Contact.objects.filter(tenant=tenant)
        .select_related("account")
        .annotate(
            channel_name=Subquery(
                chat.filter(direction=Message.DIRECTION_IN)
                .order_by("-id")
                .values("contact_name")[:1]
            ),
            last_contact_at=Subquery(chat.order_by("-id").values("created_at")[:1]),
        )
    )


class ContactListView(generics.GenericAPIView):
    """GET /api/v1/crm/contacts/ → the contacts of the active business, for any member."""

    permission_classes = [IsAuthenticated, HasActiveTenant]
    serializer_class = ContactSerializer

    @extend_schema(
        # A plain GenericAPIView is taken for a retrieve; the name tells it from the file's
        operation_id="v1_crm_contacts_list",
        parameters=[ContactsQuerySerializer],
        responses={
            200: inline_serializer(
                "ContactListResponse",
                {
                    "success": serializers.BooleanField(),
                    "data": inline_serializer(
                        "ContactList",
                        {
                            "contacts": ContactSerializer(many=True),
                            "has_more": serializers.BooleanField(),
                        },
                    ),
                },
            )
        },
    )
    def get(self, request):
        query = ContactsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        limit, offset = query.validated_data["limit"], query.validated_data["offset"]
        contacts = contacts_of(request.tenant)
        # The id breaks the ties, so a page never repeats or skips a contact
        contacts = contacts.order_by(F("last_contact_at").desc(nulls_last=True), "id")
        page = list(contacts[offset : offset + limit + 1])
        data = {
            "contacts": ContactSerializer(page[:limit], many=True).data,
            "has_more": len(page) > limit,
        }
        return Response({"success": True, "data": data})


class ContactDetailView(generics.GenericAPIView):
    """GET /api/v1/crm/contacts/<id>/ → the file of a contact of the active business."""

    permission_classes = [IsAuthenticated, HasActiveTenant]
    serializer_class = ContactFileSerializer

    @extend_schema(
        responses={
            200: inline_serializer(
                "ContactFileResponse",
                {"success": serializers.BooleanField(), "data": ContactFileSerializer()},
            )
        }
    )
    def get(self, request, contact_id):
        return Response(
            {"success": True, "data": ContactFileSerializer(self.file_of(contact_id)).data}
        )

    @extend_schema(
        request=ContactEditSerializer,
        responses={
            200: inline_serializer(
                "ContactFileUpdateResponse",
                {"success": serializers.BooleanField(), "data": ContactFileSerializer()},
            )
        },
    )
    def patch(self, request, contact_id):
        edit = ContactEditSerializer(data=request.data, partial=True)
        edit.is_valid(raise_exception=True)
        contact = self.file_of(contact_id)
        for field, value in edit.validated_data.items():
            setattr(contact, field, value)
        contact.save(update_fields=[*edit.validated_data, "updated_at"])
        return Response({"success": True, "data": ContactFileSerializer(contact).data})

    def file_of(self, contact_id):
        contact = (
            contacts_of(self.request.tenant)
            .select_related("account__channel_account")
            .annotate(
                first_contact_at=Subquery(chat_of_contact().order_by("id").values("created_at")[:1])
            )
            # A contact whose account lost its link to the business cannot say where it writes
            .filter(pk=contact_id, account__channel_account__isnull=False)
            .first()
        )
        if contact is None:
            raise NotFound("Contact not found.")
        return contact
