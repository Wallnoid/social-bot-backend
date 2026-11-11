"""
Models of the inbox.
"""

from django.db import models
from wanps.messaging.models import Message


class MessageFile(models.Model):
    """
    A file of a message that was saved the first time somebody opened it.

    It is a cache of what Meta gave: it can be deleted at any time (and is, after a while)
    and asked for again, so it is removed for real and does not use soft delete.
    """

    message = models.OneToOneField(Message, on_delete=models.CASCADE, related_name="saved_file")
    path = models.CharField(max_length=255, help_text="Where the storage keeps the file.")
    mime_type = models.CharField(max_length=127)
    size = models.PositiveBigIntegerField(help_text="Bytes.")
    created_at = models.DateTimeField(auto_now_add=True, help_text="When it was saved.")

    def __str__(self) -> str:
        return f"{self.path} ({self.size} bytes)"
