from django.apps import AppConfig


class ConversationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.conversations"
    verbose_name = "Conversations"

    def ready(self):
        # Listen to what wanps-core announces, to tell the connected members (see events.py)
        from . import events  # noqa: F401
