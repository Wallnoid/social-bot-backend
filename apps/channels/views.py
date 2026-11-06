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
    """PATCH /api/v1/channels/accounts/<id>/ → edit an account of the active business."""

    serializer_class = UpdateAccountSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, IsTenantAdmin]

    @extend_schema(
        responses={
            200: inline_serializer(
                "ChannelAccountResponse",
                {"success": serializers.BooleanField(), "data": ChannelAccountSerializer()},
            )
        }
    )
    def patch(self, request, account_id):
        # Only this business's accounts are looked up: another business's is simply not found
        links = ChannelAccount.objects.filter(tenant=request.tenant).select_related("account")
        link = get_object_or_404(links, pk=account_id)
        serializer = self.get_serializer(link.account, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True, "data": ChannelAccountSerializer(link).data})
