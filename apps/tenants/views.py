"""
Views for the tenants app.
"""

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.core.throttling import BurstAnonRateThrottle, BurstUserRateThrottle

from .emails import send_invitation_email
from .models import Invitation, Membership, Tenant
from .permissions import HasActiveTenant, IsTenantAdmin
from .serializers import (
    InvitationAcceptSerializer,
    InvitationLookupSerializer,
    InvitationSerializer,
    InviterSerializer,
    MemberSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()

NEXT_STEPS = ["create_account", "log_in", "create_password"]


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
    GET /api/v1/tenants/invitations/ → the pending invitations of the active business.
    POST /api/v1/tenants/invitations/ → invite a person to the active business.
    """

    serializer_class = InvitationSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, IsTenantAdmin]

    def get_throttles(self):
        # Only inviting sends email, so only inviting gets the tight limit
        if self.request.method == "POST":
            return [BurstUserRateThrottle()]
        return super().get_throttles()

    @extend_schema(
        responses={
            200: inline_serializer(
                "InvitationListResponse",
                {"success": serializers.BooleanField(), "data": InvitationSerializer(many=True)},
            )
        }
    )
    def get(self, request):
        invitations = (
            Invitation.pending().filter(tenant=request.tenant).select_related("invited_by")
        )
        return Response({"success": True, "data": self.get_serializer(invitations, many=True).data})

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


class InvitationDetailView(generics.GenericAPIView):
    """
    DELETE /api/v1/tenants/invitations/<id>/ → cancel a pending invitation.
    """

    permission_classes = [IsAuthenticated, HasActiveTenant, IsTenantAdmin]

    @extend_schema(
        responses={
            200: inline_serializer(
                "InvitationCancelledResponse",
                {"success": serializers.BooleanField(), "message": serializers.CharField()},
            )
        }
    )
    def delete(self, request, invitation_id):
        # Accepting locks the invitation too, so only one of the two can win
        with transaction.atomic():
            lock_business_as_admin(request)
            invitation = get_object_or_404(
                Invitation.pending().select_for_update().filter(tenant=request.tenant),
                pk=invitation_id,
            )
            invitation.soft_delete()
        return Response({"success": True, "message": "Invitation cancelled."})


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

    @extend_schema(
        responses={
            200: inline_serializer(
                "InvitationLookupResponse",
                {
                    "success": serializers.BooleanField(),
                    "data": inline_serializer(
                        "InvitationLookupData",
                        {
                            "tenant": serializers.CharField(),
                            "email": serializers.EmailField(),
                            "role": serializers.ChoiceField(choices=Membership.Role.choices),
                            "invited_by": InviterSerializer(),
                            "expires_at": serializers.DateTimeField(),
                            "has_account": serializers.BooleanField(),
                            "next_step": serializers.ChoiceField(choices=NEXT_STEPS),
                        },
                    ),
                },
            )
        }
    )
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
                    "invited_by": InviterSerializer(invitation.invited_by).data,
                    "expires_at": serializers.DateTimeField().to_representation(
                        invitation.expires_at
                    ),
                    "has_account": user is not None,
                    "next_step": next_step,
                },
            }
        )


class InvitationAcceptView(generics.GenericAPIView):
    """
    POST /api/v1/tenants/invitations/accept/ → join the business of an invitation.
    """

    serializer_class = InvitationAcceptSerializer
    # JWT only: an existing account sends its token, and the Django admin cookie must not ask
    # the frontend for a CSRF token
    authentication_classes = [JWTAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [BurstAnonRateThrottle, BurstUserRateThrottle]

    @extend_schema(
        responses={
            201: inline_serializer(
                "InvitationAcceptResponse",
                {
                    "success": serializers.BooleanField(),
                    "data": inline_serializer(
                        "InvitationAcceptData",
                        {
                            "tenant": serializers.CharField(),
                            "role": serializers.ChoiceField(choices=Membership.Role.choices),
                        },
                    ),
                },
            )
        }
    )
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


def other_members(request):
    """The members of the active business, without the admin asking."""
    return (
        Membership.objects.filter(tenant=request.tenant)
        .exclude(user=request.user)
        .select_related("user")
    )


def lock_business_as_admin(request):
    """
    Call inside a transaction, before an admin-only change. The lock makes the
    admins of a business act one at a time, and the role is read again under it,
    so an admin demoted while their request was on its way cannot act.
    """
    get_object_or_404(Tenant.objects.select_for_update(no_key=True), pk=request.tenant.pk)
    if not Membership.objects.filter(
        tenant=request.tenant, user=request.user, role=Membership.Role.ADMIN
    ).exists():
        raise PermissionDenied


def cancel_invitations_sent_by(member):
    """Keep someone who lost admin access from coming back through their own invitations."""
    for invitation in Invitation.objects.filter(tenant=member.tenant, invited_by=member.user):
        invitation.soft_delete()


class MemberListView(generics.GenericAPIView):
    """
    GET /api/v1/tenants/members/ → the members of the active business, without
    the admin asking.
    """

    serializer_class = MemberSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, IsTenantAdmin]

    @extend_schema(
        responses={
            200: inline_serializer(
                "MemberListResponse",
                {"success": serializers.BooleanField(), "data": MemberSerializer(many=True)},
            )
        }
    )
    def get(self, request):
        members = other_members(request)
        return Response({"success": True, "data": self.get_serializer(members, many=True).data})


class MemberDetailView(generics.GenericAPIView):
    """
    PATCH /api/v1/tenants/members/<id>/ → change the role of a member.
    DELETE /api/v1/tenants/members/<id>/ → remove a member from the business.
    """

    serializer_class = MemberSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, IsTenantAdmin]

    def get_member(self, request, member_id):
        """Call inside a transaction, so two admins demoting each other leave one admin."""
        lock_business_as_admin(request)
        return get_object_or_404(other_members(request), pk=member_id)

    @extend_schema(
        # A plain schema, because the generator makes every serializer field optional on PATCH
        request={
            "application/json": {
                "type": "object",
                "properties": {"role": {"type": "string", "enum": Membership.Role.values}},
                "required": ["role"],
            }
        },
        responses={
            200: inline_serializer(
                "MemberResponse",
                {"success": serializers.BooleanField(), "data": MemberSerializer()},
            )
        },
    )
    def patch(self, request, member_id):
        with transaction.atomic():
            member = self.get_member(request, member_id)
            serializer = self.get_serializer(member, data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            if member.role != Membership.Role.ADMIN:
                cancel_invitations_sent_by(member)
        return Response({"success": True, "data": serializer.data})

    @extend_schema(
        responses={
            200: inline_serializer(
                "MemberRemovedResponse",
                {"success": serializers.BooleanField(), "message": serializers.CharField()},
            )
        }
    )
    def delete(self, request, member_id):
        with transaction.atomic():
            member = self.get_member(request, member_id)
            member.soft_delete()
            cancel_invitations_sent_by(member)
        return Response({"success": True, "message": "Member removed."})
