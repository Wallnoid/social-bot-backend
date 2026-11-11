from django.apps import AppConfig
from django.conf import settings


class DevToolsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.devtools"
    label = "devtools"
    verbose_name = "Development tools"

    def ready(self):
        # Only while developing, and only if asked for: otherwise real Meta accounts keep working
        if getattr(settings, "META_FAKE", False) and settings.DEBUG:
            from . import fake_meta

            fake_meta.install()
