"""
Permission classes for the accounts app.
"""

from rest_framework.permissions import BasePermission


class IsAccountOwner(BasePermission):
    """
    Object-level permission that only allows users to
    view/edit their own account, staff included.
    """

    def has_object_permission(self, request, view, obj):
        return obj == request.user
