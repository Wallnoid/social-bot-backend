"""
Root URL configuration.

Includes API routes, admin panel, API documentation, and health checks.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from health_check.views import HealthCheckView
from wanps.messaging.meta import MetaWebhookView

urlpatterns = [
    # Redirect root to documentation
    path("", RedirectView.as_view(pattern_name="swagger-ui", permanent=False), name="index"),
    # Admin
    path("admin/", admin.site.urls),
    # API v1
    path("api/v1/", include([
        path("accounts/", include("apps.accounts.urls")),
        path("tenants/", include("apps.tenants.urls")),
        path("channels/", include("apps.channels.urls")),
    ])),
    # Meta webhook (WhatsApp, Messenger, Instagram), served by wanps-core. Only the
    # per-app route: the one without a key has no app secret to check signatures.
    path(
        "webhooks/meta/",
        include(
            (
                [path("<str:webhook_key>/", MetaWebhookView.as_view(), name="meta-webhook")],
                "messaging",
            )
        ),
    ),
    # API Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
    # Health Checks (django-health-check v4.x)
    path(
        "health/",
        HealthCheckView.as_view(
            checks=[
                "health_check.Database",
                "health_check.Cache",
                "health_check.Storage",
            ]
        ),
        name="health-check",
    ),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Customize admin site
admin.site.site_header = "Social Bot"
admin.site.site_title = "Social Bot Admin"
admin.site.index_title = "Administration"
