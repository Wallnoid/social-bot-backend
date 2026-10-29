"""
Custom middleware for the project.
"""

import logging
import time

logger = logging.getLogger("apps.core.middleware")


class RequestLoggingMiddleware:
    """
    Middleware that logs every HTTP request with method, path,
    status code, and response time.

    Log format:
        INFO [GET] /api/v1/accounts/me/ → 200 (45ms)
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.monotonic()

        response = self.get_response(request)

        # Calculate response time
        duration_ms = (time.monotonic() - start_time) * 1000

        # Skip logging for static files and health checks
        path = request.path
        skip_paths = ("/static/", "/media/", "/health/", "/favicon.ico")
        if not any(path.startswith(p) for p in skip_paths):
            logger.info(
                "[%s] %s → %s (%.0fms)",
                request.method,
                path,
                response.status_code,
                duration_ms,
            )

        return response


class CORSDebugMiddleware:
    """
    Debug middleware to log CORS-related headers.
    Only use in development.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.META.get("HTTP_ORIGIN"):
            logger.debug(
                "CORS request from origin: %s",
                request.META["HTTP_ORIGIN"],
            )

        return response
