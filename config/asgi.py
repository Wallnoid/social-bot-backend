"""
ASGI config for the Django project.

It exposes the ASGI callable as a module-level variable named ``application``: normal HTTP goes
to Django, and the permanent connection of the inbox (WebSocket) goes to its consumer.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import OriginValidator
from django.conf import settings
from django.core.asgi import get_asgi_application
from django.urls import path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

# Django must be set up before the consumers (which use models) are imported
django_asgi_application = get_asgi_application()

from apps.conversations.consumers import InboxConsumer  # noqa: E402


class FrontendOriginValidator:
    """
    Only the pages of the frontend open the permanent connection: the origins in
    `CORS_ALLOWED_ORIGINS`, read on every connection. A connection without an origin is not a
    browser, so it is refused too, unless CORS allows every origin (development).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Only the local settings define it (production leaves CORS closed by not defining it)
        open_cors = getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False)
        allowed = ["*"] if open_cors else settings.CORS_ALLOWED_ORIGINS
        return await OriginValidator(self.app, allowed)(scope, receive, send)


application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": FrontendOriginValidator(
            URLRouter([path("ws/inbox/", InboxConsumer.as_asgi())])
        ),
    }
)
