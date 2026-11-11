"""
API docs: the header that names the active business.
"""

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
        if HasActiveTenant in getattr(self.view, "permission_classes", []):
            parameters = [*parameters, TENANT_HEADER]
        return parameters
