"""
Permission classes for the tenants app.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import BasePermission

from .models import Membership


class HasActiveTenant(BasePermission):
    """
    Resolves the business the user is working in from the X-Tenant-ID header.

    On success it sets `request.tenant` and `request.membership` for the view.
    """

    def has_permission(self, request, view):
        memberships = request.user.memberships.select_related("tenant").filter(
            tenant__is_deleted=False
        )
        tenant_id = request.headers.get("X-Tenant-ID", "").strip()
        if tenant_id:
            try:
                membership = memberships.get(tenant_id=tenant_id)
            except (Membership.DoesNotExist, DjangoValidationError):
                raise NotFound("Business not found.") from None
        else:
            found = list(memberships[:2])
            if not found:
                raise NotFound("You do not belong to any business.")
            if len(found) > 1:
                raise ValidationError(
                    "Choose the business you work in with the X-Tenant-ID header."
                )
            membership = found[0]
        request.membership = membership
        request.tenant = membership.tenant
        return True


class IsTenantAdmin(BasePermission):
    """Allows only admins of the active business; use after HasActiveTenant."""

    def has_permission(self, request, view):
        return request.membership.role == Membership.Role.ADMIN
