"""
API docs: the header that names the active business.
"""

import contextlib

from drf_spectacular.openapi import AutoSchema
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter

from .permissions import HasActiveTenant

TENANT_HEADER = OpenApiParameter(
    "X-Tenant-ID",
    OpenApiTypes.UUID,
    OpenApiParameter.HEADER,
    required=False,
    description="The business to work in. Optional for a user who belongs to only one business; "
    "with several, leaving it out answers 400.",
)


class TenantAutoSchema(AutoSchema):
    """Adds `X-Tenant-ID` to every view that works inside a business (`HasActiveTenant`)."""

    def get_override_parameters(self):
        parameters = super().get_override_parameters()
        if HasActiveTenant in self.permission_classes_of_view():
            parameters = [*parameters, TENANT_HEADER]
        return parameters

    def permission_classes_of_view(self):
        """The class attribute, and what `get_permissions()` picks (some views choose per method)."""
        classes = list(getattr(self.view, "permission_classes", []))
        # The docs must build even if a view needs a real request
        with contextlib.suppress(Exception):
            classes += [type(permission) for permission in self.view.get_permissions()]
        return classes
