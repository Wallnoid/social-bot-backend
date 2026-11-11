"""
Views for the channels app.
"""

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from wanps.messaging.models import App

from apps.tenants.models import Tenant
from apps.tenants.permissions import HasActiveTenant, IsTenantAdmin

from .models import ChannelAccount, SharedMetaApp, meta_app_for
from .serializers import (
    ALREADY_CONNECTED,
    ChannelAccountSerializer,
    ConnectAccountSerializer,
    MetaAppSerializer,
    UpdateAccountSerializer,
)
from .services import disconnect


class MetaAppNotSetUp(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = (
        "Channels are not set up for this business yet. Contact Social Bot to set up a Meta App."
    )
    default_code = "meta_app_not_set_up"


class ChannelAccountListView(generics.GenericAPIView):
    """
    GET /api/v1/channels/accounts/ → the accounts of the active business, for any member.
    POST /api/v1/channels/accounts/ → connect an account to the active business, for admins.
    """

    serializer_class = ConnectAccountSerializer

    def get_permissions(self):
        permissions = [IsAuthenticated, HasActiveTenant]
        if self.request.method == "POST":
            permissions.append(IsTenantAdmin)
        return [permission() for permission in permissions]

    @extend_schema(
        responses={
            200: inline_serializer(
                "ChannelAccountListResponse",
                {
                    "success": serializers.BooleanField(),
                    "data": ChannelAccountSerializer(many=True),
                },
            )
        }
    )
    def get(self, request):
        links = ChannelAccount.objects.filter(tenant=request.tenant).select_related("account")
        return Response(
            {
                "success": True,
                "data": ChannelAccountSerializer(links.order_by("created_at"), many=True).data,
            }
        )

    @extend_schema(
        responses={
            201: inline_serializer(
                "ChannelAccountConnectedResponse",
                {"success": serializers.BooleanField(), "data": ChannelAccountSerializer()},
            )
        }
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        app = meta_app_for(request.tenant)
        if app is None:
            raise MetaAppNotSetUp
        try:
            with transaction.atomic():
                # Starts inactive: messages are stored but the bot does not reply yet
                account = serializer.save(app=app, is_active=False)
                link = ChannelAccount.objects.create(tenant=request.tenant, account=account)
        except IntegrityError:
            # Another request connected the same account after this one was validated
            raise ValidationError({"non_field_errors": [ALREADY_CONNECTED]}) from None
        return Response(
            {"success": True, "data": ChannelAccountSerializer(link).data},
            status=status.HTTP_201_CREATED,
        )


class ChannelAccountDetailView(generics.GenericAPIView):
    """
    PATCH /api/v1/channels/accounts/<id>/ → edit an account of the active business.
    DELETE /api/v1/channels/accounts/<id>/ → disconnect it.
    """

    serializer_class = UpdateAccountSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, IsTenantAdmin]

    def get_locked_link(self, request, account_id):
        """
        Call inside a transaction: the row stays locked, so an edit and a disconnection of
        the same account never run together. Only this business's accounts are looked up:
        another business's (or a disconnected one) is simply not found.
        """
        links = (
            ChannelAccount.objects.select_for_update()
            .filter(tenant=request.tenant)
            .select_related("account")
        )
        return get_object_or_404(links, pk=account_id)

    @extend_schema(
        responses={
            200: inline_serializer(
                "ChannelAccountResponse",
                {"success": serializers.BooleanField(), "data": ChannelAccountSerializer()},
            )
        }
    )
    def patch(self, request, account_id):
        with transaction.atomic():
            link = self.get_locked_link(request, account_id)
            serializer = self.get_serializer(link.account, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response({"success": True, "data": ChannelAccountSerializer(link).data})

    @extend_schema(
        responses={
            200: inline_serializer(
                "ChannelAccountDisconnectedResponse",
                {"success": serializers.BooleanField(), "message": serializers.CharField()},
            )
        }
    )
    def delete(self, request, account_id):
        with transaction.atomic():
            link = self.get_locked_link(request, account_id)
            disconnect(link)
        return Response({"success": True, "message": "Account disconnected."})


def is_used_by_others(app, tenant):
    """
    Whether the Meta App is also used by the Social Bot team's shared app or by another business.

    Such an app is not the business's own to see or change.
    """
    return (
        SharedMetaApp.objects.filter(app=app).exists()
        or Tenant.objects.filter(meta_app=app).exclude(pk=tenant.pk).exists()
    )


def envelope(name, data):
    """The shape of a successful answer, for the API docs."""
    return inline_serializer(name, {"success": serializers.BooleanField(), "data": data})


class MetaAppView(generics.GenericAPIView):
    """
    GET /api/v1/channels/meta-app/ → the Meta App of the active business (null if it has none).
    POST /api/v1/channels/meta-app/ → set it up.
    PATCH /api/v1/channels/meta-app/ → edit it or deactivate it.
    """

    serializer_class = MetaAppSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, IsTenantAdmin]

    @extend_schema(
        responses={200: envelope("MetaAppReadResponse", MetaAppSerializer(allow_null=True))}
    )
    def get(self, request):
        app = request.tenant.meta_app
        if app is None:
            return Response({"success": True, "data": None})
        if is_used_by_others(app, request.tenant):
            # Not this business's app to see or change: only enough to know it is in use
            data = {"name": app.name, "is_active": app.is_active, "shared": True}
        else:
            data = self.get_serializer(app).data
        return Response({"success": True, "data": data})

    @extend_schema(responses={201: envelope("MetaAppCreatedResponse", MetaAppSerializer())})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            # Locked, so two requests of the same business cannot each set one up
            tenant = Tenant.objects.select_for_update(no_key=True).get(pk=request.tenant.pk)
            if tenant.meta_app_id is not None:
                raise ValidationError(
                    {"non_field_errors": ["This business already has a Meta App. Edit it instead."]}
                )
            tenant.meta_app = serializer.save()
            tenant.save(update_fields=["meta_app", "updated_at"])
        return Response(
            {"success": True, "data": self.get_serializer(tenant.meta_app).data},
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(responses={200: envelope("MetaAppEditedResponse", MetaAppSerializer())})
    def patch(self, request):
        if request.tenant.meta_app_id is None:
            raise NotFound("This business has no Meta App yet.")
        with transaction.atomic():
            # Locked, so the Social Bot team cannot share it with another business half way
            app = App.objects.select_for_update(no_key=True).get(pk=request.tenant.meta_app_id)
            if is_used_by_others(app, request.tenant):
                raise PermissionDenied("This Meta App is shared with other businesses.")
            serializer = self.get_serializer(app, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response({"success": True, "data": serializer.data})
