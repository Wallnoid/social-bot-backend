"""
Custom exception handler for consistent API error responses.

All API errors follow a standard format:
{
    "success": false,
    "message": "Error description",
    "errors": { ... }  // field-level errors if applicable
}
"""

import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    ValidationError as DRFValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler that returns consistent error responses.

    Handles:
    - DRF ValidationError → 400 with field errors
    - Django ValidationError → 400 with field errors
    - Http404 → 404
    - All other DRF exceptions → appropriate status code
    - Unhandled exceptions → 500 (logged)
    """

    # Convert Django ValidationError to DRF ValidationError
    if isinstance(exc, DjangoValidationError):
        if hasattr(exc, "message_dict"):
            exc = DRFValidationError(detail=exc.message_dict)
        else:
            exc = DRFValidationError(detail=exc.messages)

    # Call DRF's default exception handler first
    response = exception_handler(exc, context)

    if response is not None:
        # Format the response
        error_payload = {
            "success": False,
            "status_code": response.status_code,
            "message": _get_error_message(exc, response),
        }

        # Add field-level errors for validation errors
        if isinstance(exc, DRFValidationError):
            error_payload["errors"] = response.data
        elif isinstance(response.data, dict):
            error_payload["errors"] = response.data

        response.data = error_payload

    else:
        # Unhandled exceptions — log and return 500
        logger.exception(
            "Unhandled exception in %s",
            context.get("view", "unknown view"),
            exc_info=exc,
        )
        error_payload = {
            "success": False,
            "status_code": 500,
            "message": "An unexpected error occurred. Please try again later.",
        }
        response = Response(
            error_payload,
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return response


def _get_error_message(exc, response):
    """Extract a human-readable error message from the exception."""
    if isinstance(exc, Http404):
        return "Resource not found."
    if isinstance(exc, DRFValidationError):
        return "Validation error. Please check the provided data."
    if isinstance(exc, APIException):
        return str(exc.detail) if hasattr(exc, "detail") else str(exc)
    return "An error occurred."
