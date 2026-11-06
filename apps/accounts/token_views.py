"""
Login, refresh and logout with the refresh token in an httpOnly cookie.

SimpleJWT issues, rotates and revokes the tokens; these views only decide where the
refresh token travels: in a cookie that the page cannot read, never in a body.
"""

import contextlib

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import (
    TokenBlacklistView,
    TokenObtainPairView,
    TokenRefreshView,
)

ACCESS_ONLY = inline_serializer("AccessToken", {"access": serializers.CharField()})

CUSTOM_HEADER = OpenApiParameter(
    "X-Requested-With",
    OpenApiTypes.STR,
    OpenApiParameter.HEADER,
    required=True,
    description="Any value. The refresh token travels in a cookie, so this header proves the "
    "request comes from the app and not from a form on another site.",
)


def require_custom_header(request):
    """
    A cookie travels by itself, so a form on another site could make the browser send it.
    Such a form cannot add this header, and a script on another site is stopped by CORS.
    """
    if not request.headers.get("X-Requested-With"):
        raise PermissionDenied("The X-Requested-With header is required.")


def cookie_scope():
    """What identifies the cookie: setting and deleting it must use the same, or it stays."""
    return {"path": settings.AUTH_REFRESH_COOKIE_PATH, "samesite": "Strict"}


def delete_refresh_cookie(response):
    response.delete_cookie(settings.AUTH_REFRESH_COOKIE_NAME, **cookie_scope())


def set_refresh_cookie(response, token):
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        token,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        httponly=True,
        **cookie_scope(),
    )


class CookieTokenObtainPairView(TokenObtainPairView):
    """Login: the access token in the body, the refresh token in the cookie."""

    @extend_schema(responses={200: ACCESS_ONLY})
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            set_refresh_cookie(response, response.data.pop("refresh"))
        return response


class CookieTokenRefreshView(TokenRefreshView):
    """Refresh: the cookie in, a new access token in the body and a new cookie out."""

    @extend_schema(
        request=None,
        parameters=[CUSTOM_HEADER],
        responses={
            200: ACCESS_ONLY,
            401: OpenApiResponse(description="The cookie is missing, expired or revoked."),
            403: OpenApiResponse(description="The X-Requested-With header is missing."),
        },
    )
    def post(self, request, *args, **kwargs):
        require_custom_header(request)
        token = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if not token:
            raise InvalidToken("The refresh cookie is missing.")
        serializer = self.get_serializer(data={"refresh": token})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        data = dict(serializer.validated_data)
        refresh = data.pop("refresh", None)
        response = Response(data)
        if refresh:
            set_refresh_cookie(response, refresh)
        return response


class CookieTokenBlacklistView(TokenBlacklistView):
    """Logout: revoke the token of the cookie and delete the cookie."""

    @extend_schema(
        request=None,
        parameters=[CUSTOM_HEADER],
        responses={
            200: OpenApiResponse(description="The cookie is deleted, even if it was not valid."),
            403: OpenApiResponse(description="The X-Requested-With header is missing."),
        },
    )
    def post(self, request, *args, **kwargs):
        require_custom_header(request)
        token = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if token:
            # Expired, already revoked or not a token: there is nothing left to revoke
            with contextlib.suppress(TokenError):
                RefreshToken(token).blacklist()
        response = Response({})
        delete_refresh_cookie(response)
        return response
