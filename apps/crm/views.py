"""
Views for the crm app.
"""

from django.db import transaction
from django.db.models import Count, F, OuterRef, Q, Subquery
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from wanps.messaging.models import Message

from apps.tenants.permissions import HasActiveTenant, IsTenantAdmin

from .models import Contact, Stage
from .serializers import (
    ContactEditSerializer,
    ContactFileSerializer,
    ContactSerializer,
    ContactsQuerySerializer,
    StageDeleteQuerySerializer,
    StageNameSerializer,
    StageOrderSerializer,
    StageSerializer,
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
        .select_related("account", "stage")
        .annotate(
            channel_name=Subquery(
                chat.filter(direction=Message.DIRECTION_IN)
                .order_by("-id")
                .values("contact_name")[:1]
            ),
            last_contact_at=Subquery(chat.order_by("-id").values("created_at")[:1]),
        )
    )


def stages_of(tenant):
    """The stages of the pipeline of a business in order, with how many contacts each has."""
    return (
        Stage.objects.filter(tenant=tenant)
        .annotate(contact_count=Count("contacts", filter=Q(contacts__is_deleted=False)))
        # A query that counts does not take the order of the model
        .order_by("position")
    )


def lock_stages_of(tenant):
    """
    Lock the stages of a business until the transaction ends, so changes to its pipeline
    happen one at a time. Every change to the stages takes this lock.
    """
    return list(Stage.objects.select_for_update().filter(tenant=tenant))


def stage_among(stages, stage_id):
    """The stage with that id among the stages of the business, else 404."""
    stage = next((stage for stage in stages if str(stage.pk) == str(stage_id)), None)
    if stage is None:
        raise NotFound("Stage not found.")
    return stage


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
        if "stage" in query.validated_data:
            contacts = contacts.filter(stage_id=query.validated_data["stage"])
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
        edit = ContactEditSerializer(data=request.data, partial=True, context={"request": request})
        edit.is_valid(raise_exception=True)
        # Looked up once the body is valid: an invalid edit does not run the query of the file
        edit.instance = self.file_of(contact_id)
        contact = edit.save()
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


class StageListView(generics.GenericAPIView):
    """
    GET /api/v1/crm/stages/ → the stages of the pipeline of the active business, in order.
    POST /api/v1/crm/stages/ → add a stage at the end of the pipeline, for admins.
    """

    serializer_class = StageSerializer

    def get_permissions(self):
        permissions = [IsAuthenticated, HasActiveTenant]
        if self.request.method == "POST":
            permissions.append(IsTenantAdmin)
        return [permission() for permission in permissions]

    @extend_schema(
        request=StageNameSerializer,
        responses={
            201: inline_serializer(
                "StageCreatedResponse",
                {"success": serializers.BooleanField(), "data": StageSerializer()},
            )
        },
    )
    def post(self, request):
        with transaction.atomic():
            # Locked, so two stages created at once get neither the same position nor the
            # same name
            current = lock_stages_of(request.tenant)
            body = StageNameSerializer(data=request.data, context={"request": request})
            body.is_valid(raise_exception=True)
            stage = Stage.objects.create(
                tenant=request.tenant,
                name=body.validated_data["name"],
                position=max((stage.position + 1 for stage in current), default=0),
            )
        stage.contact_count = 0
        return Response(
            {"success": True, "data": StageSerializer(stage).data}, status=status.HTTP_201_CREATED
        )

    @extend_schema(
        operation_id="v1_crm_stages_list",
        responses={
            200: inline_serializer(
                "StageListResponse",
                {
                    "success": serializers.BooleanField(),
                    "data": inline_serializer("StageList", {"stages": StageSerializer(many=True)}),
                },
            )
        },
    )
    def get(self, request):
        return Response(
            {
                "success": True,
                "data": {"stages": StageSerializer(stages_of(request.tenant), many=True).data},
            }
        )


class StageDetailView(generics.GenericAPIView):
    """
    PATCH /api/v1/crm/stages/<id>/ → rename a stage of the active business, for admins.
    DELETE /api/v1/crm/stages/<id>/ → delete a stage of the active business, for admins.
    """

    permission_classes = [IsAuthenticated, HasActiveTenant, IsTenantAdmin]
    serializer_class = StageSerializer

    @extend_schema(
        request=StageNameSerializer,
        responses={
            200: inline_serializer(
                "StageUpdatedResponse",
                {"success": serializers.BooleanField(), "data": StageSerializer()},
            )
        },
    )
    def patch(self, request, stage_id):
        with transaction.atomic():
            # Locked, so two stages renamed at once do not end with the same name
            stage = stage_among(lock_stages_of(request.tenant), stage_id)
            body = StageNameSerializer(stage, data=request.data, context={"request": request})
            body.is_valid(raise_exception=True)
            stage.name = body.validated_data["name"]
            stage.save(update_fields=["name", "updated_at"])
        return Response(
            {
                "success": True,
                "data": StageSerializer(stages_of(request.tenant).get(pk=stage.pk)).data,
            }
        )

    @extend_schema(
        parameters=[StageDeleteQuerySerializer],
        responses={
            200: inline_serializer(
                "StageDeletedResponse",
                {"success": serializers.BooleanField(), "message": serializers.CharField()},
            )
        },
    )
    def delete(self, request, stage_id):
        query = StageDeleteQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        with transaction.atomic():
            # Every stage of the business locked: two admins deleting at once cannot leave it
            # without stages, nor move contacts to a stage being deleted
            current = lock_stages_of(request.tenant)
            stage = stage_among(current, stage_id)
            if len(current) == 1:
                raise ValidationError(
                    {
                        "non_field_errors": [
                            "The pipeline needs at least one stage: this is the last one."
                        ]
                    }
                )
            others = sorted(
                (other for other in current if other.pk != stage.pk), key=lambda o: o.position
            )
            if Contact.objects.filter(stage=stage).exists():
                move_to = next(
                    (o for o in others if o.pk == query.validated_data.get("move_to")), None
                )
                if move_to is None:
                    raise ValidationError(
                        {"move_to": "Choose another stage of the business for its contacts."}
                    )
            else:
                # Only deleted contacts, if any: the admin does not see them, so they go to the
                # first stage left
                move_to = others[0]
            # Also the deleted contacts: none is left in a stage that no longer exists
            Contact.all_objects.filter(stage=stage).update(stage=move_to, updated_at=timezone.now())
            stage.delete()
        return Response({"success": True, "message": "Stage deleted."})


class StageOrderView(generics.GenericAPIView):
    """PUT /api/v1/crm/stages/order/ → put the stages of the active business in a new order."""

    permission_classes = [IsAuthenticated, HasActiveTenant, IsTenantAdmin]
    serializer_class = StageOrderSerializer

    @extend_schema(
        responses={
            200: inline_serializer(
                "StageOrderResponse",
                {
                    "success": serializers.BooleanField(),
                    "data": inline_serializer("StageOrder", {"stages": StageSerializer(many=True)}),
                },
            )
        },
    )
    def put(self, request):
        body = StageOrderSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        order = body.validated_data["stages"]
        with transaction.atomic():
            # Locked (as creating and deleting do), so a stage created or deleted meanwhile is
            # not left out of the order
            current = lock_stages_of(request.tenant)
            if len(order) != len(set(order)) or set(order) != {stage.pk for stage in current}:
                raise ValidationError(
                    {"stages": "Send every stage of the business once, in the new order."}
                )
            now = timezone.now()
            for position, stage_id in enumerate(order):
                Stage.objects.filter(tenant=request.tenant, pk=stage_id).update(
                    position=position, updated_at=now
                )
        return Response(
            {
                "success": True,
                "data": {"stages": StageSerializer(stages_of(request.tenant), many=True).data},
            }
        )
