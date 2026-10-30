"""
Views for the tenants app.
"""

import logging

from django.db import transaction
from rest_framework import generics, status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.throttling import BurstUserRateThrottle

from .emails import send_invitation_email
from .permissions import HasActiveTenant, IsTenantAdmin
from .serializers import InvitationSerializer

logger = logging.getLogger(__name__)


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
