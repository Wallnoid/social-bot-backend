"""
Views for the accounts app.

Provides:
- User profile (me endpoint)
- Password change
- User detail/update (account owner)
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, mixins, permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.throttling import BurstAnonRateThrottle

from .permissions import IsAccountOwner
from .serializers import (
    ChangePasswordSerializer,
    PasswordResetSerializer,
    SetPasswordSerializer,
    UserProfileSerializer,
    UserSerializer,
)
from .tasks import send_password_reset_email_to
from .token_views import revoke_all_refresh_tokens, start_new_session

User = get_user_model()

PASSWORD_RESET_MESSAGE = "If an account uses this email, we sent it a link to reset the password."


class PasswordResetView(generics.GenericAPIView):
    """
    Ask for a link to reset a forgotten password.

    POST /api/v1/accounts/password-reset/

    The answer is the same whether the email has an account or not, so it does not
    reveal who uses the suite. No authentication, so a stale session token in the
    browser does not block it. The link leads to set-password.
    """

    serializer_class = PasswordResetSerializer
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [BurstAnonRateThrottle]

    @extend_schema(
        responses={
            200: inline_serializer(
                "PasswordResetResponse",
                {"success": serializers.BooleanField(), "message": serializers.CharField()},
            )
        }
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        send_password_reset_email_to.delay(serializer.validated_data["email"])
        return Response({"success": True, "message": PASSWORD_RESET_MESSAGE})


class SetPasswordView(generics.GenericAPIView):
    """
    Create a password from the link sent by email.

    POST /api/v1/accounts/set-password/
    """

    serializer_class = SetPasswordSerializer
    # No authentication: the Django admin cookie must not ask the frontend for a CSRF token
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [BurstAnonRateThrottle]

    @extend_schema(
        responses={
            200: inline_serializer(
                "SetPasswordResponse",
                {"success": serializers.BooleanField(), "message": serializers.CharField()},
            )
        }
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        with transaction.atomic():
            user.set_password(serializer.validated_data["new_password"])
            user.save()
            revoke_all_refresh_tokens(user)
        return Response(
            {"success": True, "message": "Password created successfully."}
        )


class UserViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    ViewSet for managing users.

    Endpoints:
    - GET    /api/v1/accounts/users/{id}/     → Retrieve user
    - PUT    /api/v1/accounts/users/{id}/     → Update user
    - GET    /api/v1/accounts/users/me/       → Current user profile
    - PUT    /api/v1/accounts/users/me/       → Update current user profile
    - POST   /api/v1/accounts/users/me/change-password/ → Change password
    """

    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_queryset(self):
        # Users only reach their own account; any other id looks nonexistent.
        return User.objects.filter(pk=self.request.user.pk)

    def get_permissions(self):
        if self.action in ["retrieve", "update", "partial_update"]:
            return [permissions.IsAuthenticated(), IsAccountOwner()]
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self):
        if self.action in ["update", "partial_update", "me"]:
            return UserProfileSerializer
        if self.action == "change_password":
            return ChangePasswordSerializer
        return UserSerializer

    @extend_schema(
        methods=["GET"],
        responses={
            200: inline_serializer(
                "UserProfileResponse",
                {"success": serializers.BooleanField(), "data": UserProfileSerializer()},
            )
        },
    )
    @extend_schema(
        methods=["PUT", "PATCH"],
        request=UserProfileSerializer,
        responses={
            200: inline_serializer(
                "UserProfileUpdatedResponse",
                {
                    "success": serializers.BooleanField(),
                    "message": serializers.CharField(),
                    "data": UserProfileSerializer(),
                },
            )
        },
    )
    @action(detail=False, methods=["get", "put", "patch"])
    def me(self, request):
        """
        GET: Retrieve the current authenticated user's profile.
        PUT/PATCH: Update the current authenticated user's profile.
        """
        user = request.user

        if request.method == "GET":
            serializer = self.get_serializer(user)
            return Response(
                {"success": True, "data": serializer.data}
            )

        serializer = self.get_serializer(
            user, data=request.data, partial=(request.method == "PATCH")
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "success": True,
                "message": "Profile updated successfully.",
                "data": serializer.data,
            }
        )

    @extend_schema(
        responses={
            200: inline_serializer(
                "ChangePasswordResponse",
                {
                    "success": serializers.BooleanField(),
                    "message": serializers.CharField(),
                    "access": serializers.CharField(),
                },
            )
        }
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="me/change-password",
    )
    def change_password(self, request):
        """
        Change the current user's password.

        POST /api/v1/accounts/users/me/change-password/

        Every other session is closed. This device gets a new access token in the
        body and a new refresh cookie, so it stays logged in.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        with transaction.atomic():
            user.set_password(serializer.validated_data["new_password"])
            user.save()
            revoke_all_refresh_tokens(user)

        response = Response({"success": True, "message": "Password changed successfully."})
        return start_new_session(response, user)
