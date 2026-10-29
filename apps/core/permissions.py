"""
Shared permission classes for the API.
"""

from rest_framework.permissions import BasePermission


class IsOwnerOrReadOnly(BasePermission):
    """
    Object-level permission that only allows owners of an object to edit it.

    Assumes the model instance has an 'owner' or 'user' attribute.
    Read permissions are allowed to any request (GET, HEAD, OPTIONS).
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed for any request
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True

        # Write permissions are only allowed to the owner
        owner = getattr(obj, "owner", None) or getattr(obj, "user", None)
        return owner == request.user


class IsAdminOrReadOnly(BasePermission):
    """
    Allow read access to anyone, but write access only to admin users.
    """

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return request.user and request.user.is_staff


class IsSuperUser(BasePermission):
    """
    Allow access only to superusers.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_superuser
