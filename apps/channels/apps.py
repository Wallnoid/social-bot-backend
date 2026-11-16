from django.apps import AppConfig


class ChannelsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.channels"
    verbose_name = "Channels"

    def ready(self):
        from . import failures  # noqa: F401  (a reply clears the warning of a failure)
