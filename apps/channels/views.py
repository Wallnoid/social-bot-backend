"""
Views for the channels app.
"""

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.tenants.permissions import HasActiveTenant, IsTenantAdmin

from .models import ChannelAccount, meta_app_for
from .serializers import (
    ALREADY_CONNECTED,
    ChannelAccountSerializer,
    ConnectAccountSerializer,
    UpdateAccountSerializer,
)


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
            # The wanps-core account stays, because its messages reference it: it is archived.
            # The webhook finds accounts by channel and id even when inactive, so the id is
            # freed (its events are ignored and the same number can be connected again) but
            # kept readable, cut to fit the 64 characters of the field.
            account = link.account
            account.is_active = False
            account.access_token = ""
            account.ai_api_key = ""
            account.external_id = f"{account.external_id[:40]}#disconnected-{account.pk}"
            account.save(
                update_fields=[
                    "is_active",
                    "access_token",
                    "ai_api_key",
                    "external_id",
                    "updated_at",
                ]
            )
            link.soft_delete()
        return Response({"success": True, "message": "Account disconnected."})
