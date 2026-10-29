"""
Views for the accounts app.

Provides:
- User registration
- User profile (me endpoint)
- Password change
- User list/detail (admin)
"""

from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.throttling import BurstAnonRateThrottle

from .permissions import IsAccountOwner
from .serializers import (
    ChangePasswordSerializer,
    UserCreateSerializer,
    UserProfileSerializer,
    UserSerializer,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """
    Register a new user.

    POST /api/v1/accounts/register/
    """

    queryset = User.objects.all()
    serializer_class = UserCreateSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [BurstAnonRateThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "success": True,
                "message": "User registered successfully.",
                "data": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing users.

    Endpoints:
    - GET    /api/v1/accounts/users/         → List all users (admin only)
    - POST   /api/v1/accounts/users/         → Create user (admin only)
    - GET    /api/v1/accounts/users/{id}/     → Retrieve user
    - PUT    /api/v1/accounts/users/{id}/     → Update user
    - DELETE /api/v1/accounts/users/{id}/     → Delete user (soft delete)
    - GET    /api/v1/accounts/users/me/       → Current user profile
    - PUT    /api/v1/accounts/users/me/       → Update current user profile
    - POST   /api/v1/accounts/users/me/change-password/ → Change password
    """

    queryset = User.objects.all()
    serializer_class = UserSerializer
    filterset_fields = ["is_active", "is_staff"]
    search_fields = ["email", "first_name", "last_name", "username"]
    ordering_fields = ["created_at", "email", "first_name"]

    def get_permissions(self):
        if self.action in ["list", "create", "destroy"]:
            return [permissions.IsAdminUser()]
        if self.action in ["retrieve", "update", "partial_update"]:
            return [permissions.IsAuthenticated(), IsAccountOwner()]
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
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

    def destroy(self, request, *args, **kwargs):
        """Soft delete a user (deactivate instead of hard delete)."""
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=["is_active", "updated_at"])
        return Response(
            {
                "success": True,
                "message": "User deactivated successfully.",
            },
            status=status.HTTP_200_OK,
        )
