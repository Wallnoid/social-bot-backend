"""
Periodic jobs of the channels.
"""

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import ToolCall


@shared_task(ignore_result=True)
def delete_old_tool_calls() -> int:
    """Delete the records of the calls of the tools older than the retention time."""
    limit = timezone.now() - timedelta(days=settings.TOOL_CALL_RETENTION_DAYS)
    deleted, _ = ToolCall.objects.filter(created_at__lt=limit).delete()
    return deleted
