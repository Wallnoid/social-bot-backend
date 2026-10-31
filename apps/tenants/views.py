"""
Views for the tenants app.
"""

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import generics, status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.throttling import BurstAnonRateThrottle, BurstUserRateThrottle

from .emails import send_invitation_email
from .models import Invitation, Membership
from .permissions import HasActiveTenant, IsTenantAdmin
from .serializers import (
    InvitationAcceptSerializer,
    InvitationLookupSerializer,
    InvitationSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class InvitationEmailError(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The invitation email could not be sent. Please try again."
    default_code = "invitation_email_failed"


class CurrentTenantView(APIView):
    """
    GET /api/v1/tenants/current/ → the business the user is working in and
    their role in it.
    """

    permission_classes = [IsAuthenticated, HasActiveTenant]

    def get(self, request):
        return Response(
            {
                "success": True,
                "data": {
                    "id": str(request.tenant.id),
                    "name": request.tenant.name,
                    "role": request.membership.role,
                },
            }
        )


class InvitationCreateView(generics.GenericAPIView):
    """
    POST /api/v1/tenants/invitations/ → invite a person to the active business.
    """

    serializer_class = InvitationSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, IsTenantAdmin]
    throttle_classes = [BurstUserRateThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data, context={"tenant": request.tenant})
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                invitation = serializer.save(tenant=request.tenant, invited_by=request.user)
                send_invitation_email(invitation)
        except OSError as exc:
            logger.exception("Could not send invitation email for tenant %s", request.tenant.pk)
            raise InvitationEmailError from exc
        return Response(
            {"success": True, "data": serializer.data},
            status=status.HTTP_201_CREATED,
        )


class InvitationLookupView(generics.GenericAPIView):
    """
    POST /api/v1/tenants/invitations/lookup/ → what an invitation offers and
    what the person must do to accept it. The token goes in the body so it
    never reaches the request logs. No authentication, so a stale session token
    in the browser does not block it.
    """

    serializer_class = InvitationLookupSerializer
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [BurstAnonRateThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = serializer.validated_data["invitation"]
        user = serializer.validated_data["user"]
        if user is None:
            next_step = "create_account"
        elif user.has_usable_password():
            next_step = "log_in"
        else:
            next_step = "create_password"
        return Response(
            {
                "success": True,
                "data": {
                    "tenant": invitation.tenant.name,
                    "email": invitation.email,
                    "role": invitation.role,
                    "next_step": next_step,
                },
            }
        )


class InvitationAcceptView(generics.GenericAPIView):
    """
    POST /api/v1/tenants/invitations/accept/ → join the business of an invitation.
    """

    serializer_class = InvitationAcceptSerializer
    permission_classes = [AllowAny]
    throttle_classes = [BurstAnonRateThrottle, BurstUserRateThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        with transaction.atomic():
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            invitation = data["invitation"]
            user = data["user"]
            if user is None:
                user = User.objects.create_user(
                    email=invitation.email,
                    password=data["new_password"],
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                )
            elif not user.has_usable_password():
                user.set_password(data["new_password"])
                user.save()
            Membership.objects.create(tenant=invitation.tenant, user=user, role=invitation.role)
            for used in Invitation.objects.filter(
                tenant=invitation.tenant, email__iexact=invitation.email
            ):
                used.soft_delete()
        return Response(
            {
                "success": True,
                "data": {"tenant": invitation.tenant.name, "role": invitation.role},
            },
            status=status.HTTP_201_CREATED,
        )
