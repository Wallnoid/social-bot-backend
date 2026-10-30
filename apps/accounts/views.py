"""
Views for the accounts app.

Provides:
- User profile (me endpoint)
- Password change
- User detail/update (account owner)
"""

from django.contrib.auth import get_user_model
from rest_framework import generics, mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.throttling import BurstAnonRateThrottle

from .permissions import IsAccountOwner
from .serializers import (
    ChangePasswordSerializer,
    SetPasswordSerializer,
    UserProfileSerializer,
    UserSerializer,
)

User = get_user_model()


class SetPasswordView(generics.GenericAPIView):
    """
    Create a password from the link sent by email.

    POST /api/v1/accounts/set-password/
    """

    serializer_class = SetPasswordSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [BurstAnonRateThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["new_password"])
        user.save()
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

    @action(
        detail=False,
        methods=["post"],
        url_path="me/change-password",
    )
    def change_password(self, request):
        """
        Change the current user's password.

        POST /api/v1/accounts/users/me/change-password/
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()

        return Response(
            {
                "success": True,
                "message": "Password changed successfully.",
            }
        )
