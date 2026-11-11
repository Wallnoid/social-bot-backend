"""
URL configuration for the accounts app.

Includes:
- JWT token obtain/refresh/blacklist
- User CRUD (ViewSet)
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenVerifyView

from .token_views import (
    CookieTokenBlacklistView,
    CookieTokenObtainPairView,
    CookieTokenRefreshView,
)
from .views import PasswordResetView, SetPasswordView, UserViewSet

app_name = "accounts"

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")

urlpatterns = [
    # Authentication
    path("password-reset/", PasswordResetView.as_view(), name="password_reset"),
    path("set-password/", SetPasswordView.as_view(), name="set_password"),
    path("token/", CookieTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", CookieTokenRefreshView.as_view(), name="token_refresh"),
    path("token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("token/blacklist/", CookieTokenBlacklistView.as_view(), name="token_blacklist"),
    # Users
    path("", include(router.urls)),
]
