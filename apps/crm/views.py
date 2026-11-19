"""
Views for the crm app.
"""

from django.db.models import F, OuterRef, Subquery
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from wanps.messaging.models import Message

from apps.tenants.permissions import HasActiveTenant

from .models import Contact
from .serializers import ContactSerializer, ContactsQuerySerializer


class ContactListView(generics.GenericAPIView):
    """GET /api/v1/crm/contacts/ → the contacts of the active business, for any member."""

    permission_classes = [IsAuthenticated, HasActiveTenant]
    serializer_class = ContactSerializer

    @extend_schema(
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
        # The chat of a contact, read from its messages; the latest is the one with the highest id,
        # as the inbox takes it, so both show the same name
        chat = Message.objects.filter(
            account_id=OuterRef("account_id"), contact_id=OuterRef("external_id")
        )
        contacts = (
            Contact.objects.filter(tenant=request.tenant)
            .select_related("account")
            .annotate(
                name=Subquery(
                    chat.filter(direction=Message.DIRECTION_IN)
                    .order_by("-id")
                    .values("contact_name")[:1]
                ),
                last_contact_at=Subquery(chat.order_by("-id").values("created_at")[:1]),
            )
        )
        # The id breaks the ties, so a page never repeats or skips a contact
        contacts = contacts.order_by(F("last_contact_at").desc(nulls_last=True), "id")
        page = list(contacts[offset : offset + limit + 1])
        data = {
            "contacts": ContactSerializer(page[:limit], many=True).data,
            "has_more": len(page) > limit,
        }
        return Response({"success": True, "data": data})
