"""
Views for the crm app.
"""

from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, F, OuterRef, Q, Subquery, Value
from django.db.models.functions import Greatest, Lower
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from wanps.messaging.models import Message

from apps.tenants.models import Membership
from apps.tenants.permissions import HasActiveTenant, IsTenantAdmin

from .models import Contact, Note, Stage, Tag, merge_contacts
from .serializers import (
    NOBODY,
    ContactEditSerializer,
    ContactFileSerializer,
    ContactMergeSerializer,
    ContactSerializer,
    ContactsQuerySerializer,
    NoteSerializer,
    PageQuerySerializer,
    StageDeleteQuerySerializer,
    StageNameSerializer,
    StageOrderSerializer,
    StageSerializer,
    TagCountSerializer,
    TagNameSerializer,
    TagSerializer,
)


def chat_of_contact():
    """The messages of the chat of the contact of the outer query: account, channel and client."""
    return Message.objects.filter(
        account_id=OuterRef("account_id"),
        channel=OuterRef("account__channel"),
        contact_id=OuterRef("external_id"),
    )


def channel_name_of_chat():
    """The name the channel gives to the client of the chat of the contact of the outer query."""
    # The latest message of a chat is the one with the highest id, as the inbox takes it, so
    # both show the same name
    return Subquery(
        chat_of_contact()
        .filter(direction=Message.DIRECTION_IN)
        .order_by("-id")
        .values("contact_name")[:1]
    )


def last_message_of_merged_chats():
    """When the latest message of the chats merged into the contact of the outer query was saved."""
    # The merged contacts first (almost always none), then the chat of each, as the contact's own
    return Subquery(
        Contact.all_objects.filter(merged_into=OuterRef("pk"))
        .annotate(last=Subquery(chat_of_contact().order_by("-id").values("created_at")[:1]))
        .order_by(F("last").desc(nulls_last=True))
        .values("last")[:1]
    )


def search_matches(text):
    """The contacts whose name or phone has `text`, whatever the capitalization."""
    return (
        # The name the team sees: the one the team wrote, else the channel's. On WhatsApp the
        # phone is the id of the client on the channel. A merged contact is searched with the
        # same rules (see `contacts_matching`), so its old name and phone still find the contact.
        Q(name__icontains=text)
        | Q(name="", channel_name__icontains=text)
        | Q(phone__icontains=text)
        | Q(account__channel="whatsapp", external_id__icontains=text)
    )


def contacts_matching(text):
    """The contacts that match `text` by themselves or by a contact merged into them."""
    merged = Contact.all_objects.annotate(channel_name=channel_name_of_chat()).filter(
        search_matches(text), merged_into=OuterRef("pk"), tenant=OuterRef("tenant")
    )
    return search_matches(text) | Q(Exists(merged))


def contacts_of(tenant):
    """The contacts of a business, with the name their chat gives and the last contact of all."""
    return (
        Contact.objects.filter(tenant=tenant)
        .select_related("account", "stage", "assigned_to__user")
        .prefetch_related("tags")
        .annotate(
            channel_name=channel_name_of_chat(),
            # The latest message of the chat of the contact and of the chats merged into it
            last_contact_at=Greatest(
                Subquery(chat_of_contact().order_by("-id").values("created_at")[:1]),
                last_message_of_merged_chats(),
            ),
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
        query = ContactsQuerySerializer(data=request.query_params, context={"request": request})
        query.is_valid(raise_exception=True)
        filters = query.validated_data
        limit, offset = filters["limit"], filters["offset"]
        contacts = contacts_of(request.tenant)
        if "stage" in filters:
            contacts = contacts.filter(stage_id=filters["stage"])
        if filters.get("search"):
            text = filters["search"]
            contacts = contacts.filter(contacts_matching(text))
        # One filter for each tag, so a contact needs all of them
        for tag_id in filters.get("tag", ()):
            contacts = contacts.filter(tags=tag_id)
        if filters.get("assigned_to") == NOBODY:
            # A member who left the business is no longer in charge
            contacts = contacts.filter(
                Q(assigned_to__isnull=True) | Q(assigned_to__is_deleted=True)
            )
        elif "assigned_to" in filters:
            contacts = contacts.filter(
                assigned_to_id=filters["assigned_to"], assigned_to__is_deleted=False
            )
        # The id breaks the ties, so a page never repeats or skips a contact
        contacts = contacts.order_by(F("last_contact_at").desc(nulls_last=True), "id")
        page = list(contacts[offset : offset + limit + 1])
        data = {
            "contacts": ContactSerializer(page[:limit], many=True).data,
            "has_more": len(page) > limit,
        }
        return Response({"success": True, "data": data})


class ContactFileMixin:
    """The file of a contact of the active business, shared by the views that answer with it."""

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


class ContactDetailView(ContactFileMixin, generics.GenericAPIView):
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


class ContactMergeView(ContactFileMixin, generics.GenericAPIView):
    """POST /api/v1/crm/contacts/<id>/merge/ → merge another contact into this one."""

    permission_classes = [IsAuthenticated, HasActiveTenant]
    serializer_class = ContactFileSerializer

    @extend_schema(
        request=ContactMergeSerializer,
        responses={
            200: inline_serializer(
                "ContactMergeResponse",
                {"success": serializers.BooleanField(), "data": ContactFileSerializer()},
            )
        },
    )
    def post(self, request, contact_id):
        body = ContactMergeSerializer(
            data=request.data, context={"request": request, "kept_id": contact_id}
        )
        body.is_valid(raise_exception=True)
        # Answering needs the file: a contact that cannot give it is refused before anything merges
        self.file_of(contact_id)
        with transaction.atomic():
            # Locked in a fixed order, so two merges of the same contacts do not wait for each
            # other, and read again: the contact may have been merged since the body was checked
            wanted = [contact_id, body.validated_data["contact"].pk]
            locked = {
                contact.pk: contact
                for contact in Contact.objects.select_for_update(of=("self",))
                .select_related("assigned_to")
                .filter(tenant=request.tenant, pk__in=wanted)
                .order_by("pk")
            }
            if wanted[0] not in locked:
                raise NotFound("Contact not found.")
            if wanted[1] not in locked:
                raise ValidationError({"contact": ["This contact does not exist."]})
            merge_contacts(locked[wanted[0]], locked[wanted[1]])
        return Response(
            {"success": True, "data": ContactFileSerializer(self.file_of(contact_id)).data}
        )


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


class NoteListView(generics.GenericAPIView):
    """
    GET /api/v1/crm/contacts/<id>/notes/ → the notes of a contact of the active business.
    POST /api/v1/crm/contacts/<id>/notes/ → write a note on it, as the member who asks.
    """

    permission_classes = [IsAuthenticated, HasActiveTenant]
    serializer_class = NoteSerializer

    def contact(self):
        contact = Contact.objects.filter(
            tenant=self.request.tenant, pk=self.kwargs["contact_id"]
        ).first()
        if contact is None:
            raise NotFound("Contact not found.")
        return contact

    @extend_schema(
        operation_id="v1_crm_notes_list",
        parameters=[PageQuerySerializer],
        responses={
            200: inline_serializer(
                "NoteListResponse",
                {
                    "success": serializers.BooleanField(),
                    "data": inline_serializer(
                        "NoteList",
                        {
                            "notes": NoteSerializer(many=True),
                            "has_more": serializers.BooleanField(),
                        },
                    ),
                },
            )
        },
    )
    def get(self, request, contact_id):
        query = PageQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        limit, offset = query.validated_data["limit"], query.validated_data["offset"]
        # The id breaks the ties, so a page never repeats or skips a note
        notes = (
            Note.objects.filter(contact=self.contact())
            .select_related("author")
            .order_by("-created_at", "id")
        )
        page = list(notes[offset : offset + limit + 1])
        data = {
            "notes": NoteSerializer(page[:limit], many=True).data,
            "has_more": len(page) > limit,
        }
        return Response({"success": True, "data": data})

    @extend_schema(
        request=NoteSerializer,
        responses={
            201: inline_serializer(
                "NoteCreatedResponse",
                {"success": serializers.BooleanField(), "data": NoteSerializer()},
            )
        },
    )
    def post(self, request, contact_id):
        body = NoteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        note = body.save(contact=self.contact(), author=request.user)
        return Response(
            {"success": True, "data": NoteSerializer(note).data}, status=status.HTTP_201_CREATED
        )


class NoteDetailView(generics.GenericAPIView):
    """
    PATCH /api/v1/crm/contacts/<id>/notes/<note>/ → edit a note of a contact of the business.
    DELETE /api/v1/crm/contacts/<id>/notes/<note>/ → delete it.
    """

    permission_classes = [IsAuthenticated, HasActiveTenant]
    serializer_class = NoteSerializer

    def note(self):
        note = (
            Note.objects.select_related("author")
            .filter(
                contact__tenant=self.request.tenant,
                # A filter through a relation does not skip the deleted ones by itself
                contact__is_deleted=False,
                contact_id=self.kwargs["contact_id"],
                pk=self.kwargs["note_id"],
            )
            .first()
        )
        if note is None:
            raise NotFound("Note not found.")
        return note

    @extend_schema(
        request=NoteSerializer,
        responses={
            200: inline_serializer(
                "NoteUpdatedResponse",
                {"success": serializers.BooleanField(), "data": NoteSerializer()},
            )
        },
    )
    def patch(self, request, contact_id, note_id):
        note = self.note()
        # Only its author rewrites a note, not even an admin: the words are the author's
        if note.author_id != request.user.pk:
            raise PermissionDenied("Only the author of a note can edit it.")
        body = NoteSerializer(note, data=request.data)
        body.is_valid(raise_exception=True)
        note = body.save()
        return Response({"success": True, "data": NoteSerializer(note).data})

    @extend_schema(
        responses={
            200: inline_serializer(
                "NoteDeletedResponse",
                {"success": serializers.BooleanField(), "message": serializers.CharField()},
            )
        }
    )
    def delete(self, request, contact_id, note_id):
        note = self.note()
        if note.author_id != request.user.pk and request.membership.role != Membership.Role.ADMIN:
            raise PermissionDenied("Only the author of a note or an admin can delete it.")
        note.delete()
        return Response({"success": True, "message": "Note deleted."})


def contact_of_business(request, contact_id):
    """A contact of the active business, else 404."""
    contact = Contact.objects.filter(tenant=request.tenant, pk=contact_id).first()
    if contact is None:
        raise NotFound("Contact not found.")
    return contact


def find_tag(tenant, name):
    """The tag of a business with that name, whatever the capitalization."""
    # Lower on both sides, in the database: the same comparison as the unique constraint
    return (
        Tag.objects.annotate(lowered=Lower("name"))
        .filter(tenant=tenant, lowered=Lower(Value(name)))
        .first()
    )


class ContactTagListView(generics.GenericAPIView):
    """POST /api/v1/crm/contacts/<id>/tags/ → tag a contact by the name of the tag."""

    permission_classes = [IsAuthenticated, HasActiveTenant]
    serializer_class = TagNameSerializer

    @extend_schema(
        request=TagNameSerializer,
        responses={
            201: inline_serializer(
                "ContactTaggedResponse",
                {"success": serializers.BooleanField(), "data": TagSerializer()},
            )
        },
    )
    def post(self, request, contact_id):
        body = TagNameSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        contact = contact_of_business(request, contact_id)
        name = body.validated_data["name"]
        tag = find_tag(request.tenant, name)
        if tag is None:
            try:
                # A savepoint, so a clash does not break the transaction of the request
                with transaction.atomic():
                    tag = Tag.objects.create(tenant=request.tenant, name=name)
            except IntegrityError:
                # Another request created it between the lookup and here: use that one
                tag = find_tag(request.tenant, name)
        added = not contact.tags.filter(pk=tag.pk).exists()
        contact.tags.add(tag)
        return Response(
            {"success": True, "data": TagSerializer(tag).data},
            status=status.HTTP_201_CREATED if added else status.HTTP_200_OK,
        )


class ContactTagDetailView(generics.GenericAPIView):
    """DELETE /api/v1/crm/contacts/<id>/tags/<tag>/ → take a tag off a contact."""

    permission_classes = [IsAuthenticated, HasActiveTenant]
    serializer_class = TagSerializer

    @extend_schema(
        responses={
            200: inline_serializer(
                "ContactUntaggedResponse",
                {"success": serializers.BooleanField(), "message": serializers.CharField()},
            )
        }
    )
    def delete(self, request, contact_id, tag_id):
        contact = contact_of_business(request, contact_id)
        tag = Tag.objects.filter(tenant=request.tenant, pk=tag_id).first()
        if tag is None:
            raise NotFound("Tag not found.")
        contact.tags.remove(tag)
        return Response({"success": True, "message": "Tag removed."})


class TagListView(generics.GenericAPIView):
    """GET /api/v1/crm/tags/ → the tags of the active business, with how many contacts each has."""

    permission_classes = [IsAuthenticated, HasActiveTenant]
    serializer_class = TagCountSerializer

    @extend_schema(
        operation_id="v1_crm_tags_list",
        responses={
            200: inline_serializer(
                "TagListResponse",
                {
                    "success": serializers.BooleanField(),
                    "data": inline_serializer("TagList", {"tags": TagCountSerializer(many=True)}),
                },
            )
        },
    )
    def get(self, request):
        tags = (
            Tag.objects.filter(tenant=request.tenant)
            .annotate(contact_count=Count("contacts", filter=Q(contacts__is_deleted=False)))
            # A query that counts does not take the order of the model
            .order_by("name")
        )
        return Response(
            {"success": True, "data": {"tags": TagCountSerializer(tags, many=True).data}}
        )
