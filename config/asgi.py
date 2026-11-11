"""
ASGI config for the Django project.

It exposes the ASGI callable as a module-level variable named ``application``: normal HTTP goes
to Django, and the permanent connection of the inbox (WebSocket) goes to its consumer.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

# Django must be set up before the consumers (which use models) are imported
django_asgi_application = get_asgi_application()

from apps.conversations.consumers import InboxConsumer  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": URLRouter([path("ws/inbox/", InboxConsumer.as_asgi())]),
    }
)
