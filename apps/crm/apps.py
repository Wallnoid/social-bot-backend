from django.apps import AppConfig


class CrmConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crm"
    verbose_name = "CRM"

    def ready(self):
        # A contact is created by itself from the first message of each chat (see signals.py)
        from . import signals  # noqa: F401
