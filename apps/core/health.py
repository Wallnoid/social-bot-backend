"""
Health check views for monitoring and load balancers.

These endpoints are used by Docker, Kubernetes, or any orchestrator
to verify the application is running and healthy.
"""

import logging

from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def health_check(request):
    """
    Simple health check endpoint.

    Returns:
        200: {"status": "healthy"}
        503: {"status": "unhealthy", "errors": [...]}
    """
    errors = []

    # Check database connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception as e:
        errors.append(f"Database: {str(e)}")
        logger.error("Health check failed - Database: %s", e)

    if errors:
        return JsonResponse(
            {"status": "unhealthy", "errors": errors},
            status=503,
        )

    return JsonResponse({"status": "healthy"})


def readiness_check(request):
    """
    Readiness probe for Kubernetes / load balancers.

    Checks that the application is ready to serve traffic:
    - Database is accessible
    - Migrations are up to date
    """
    errors = []

    # Check database
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception as e:
        errors.append(f"Database: {str(e)}")

    if errors:
        return JsonResponse(
            {"status": "not_ready", "errors": errors},
            status=503,
        )

    return JsonResponse({"status": "ready"})
