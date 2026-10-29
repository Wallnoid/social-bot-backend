"""
Permission classes for the accounts app.
"""

from rest_framework.permissions import BasePermission


class IsAccountOwner(BasePermission):
    """
    Object-level permission that only allows users to
    view/edit their own account.

    Admins can access any account.
    """

    def has_object_permission(self, request, view, obj):
        # Admins can access any account
        if request.user.is_staff:
            return True
        # Users can only access their own account
        return obj == request.user
