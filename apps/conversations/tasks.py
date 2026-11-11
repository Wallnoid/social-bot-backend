"""
Periodic jobs of the inbox.
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone

from .models import MessageFile

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def delete_expired_message_files() -> int:
    """Delete the saved files older than the retention time. Opening one again asks Meta again."""
    limit = timezone.now() - timedelta(days=settings.MESSAGE_FILE_RETENTION_DAYS)
    deleted = 0
    for saved in MessageFile.objects.filter(created_at__lt=limit).order_by("created_at").iterator():
        # One file that cannot be deleted must not stop the rest; it is tried again tomorrow
        try:
            default_storage.delete(saved.path)
            saved.delete()
        except Exception:
            logger.exception("Could not delete the saved file of message %s", saved.message_id)
            continue
        deleted += 1
    return deleted
