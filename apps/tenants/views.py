"""
Views for the tenants app.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import HasActiveTenant


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
