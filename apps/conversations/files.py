"""
The files of the messages: the first time one is opened it is asked of Meta through
wanps-core and saved with Django's storage; after that it is served from the storage.
"""

import logging

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from rest_framework import status
from rest_framework.exceptions import APIException
from wanps.messaging.attachments import AttachmentUnavailable, download_attachment

from .models import MessageFile

logger = logging.getLogger(__name__)


class FileTooLarge(APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_code = "file_too_large"

    def __init__(self):
        megabytes = settings.MESSAGE_FILE_MAX_BYTES // (1024 * 1024)
        super().__init__(f"The file is bigger than {megabytes} MB and cannot be opened from here.")


class FileGone(APIException):
    status_code = status.HTTP_410_GONE
    default_detail = "The file is no longer available: Meta does not keep it any more."
    default_code = "file_gone"


class FileNotReached(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = (
        "The file could not be fetched right now. Please try again in a moment. "
        "If it keeps failing, ask an admin to check the account."
    )
    default_code = "file_not_reached"


def open_message_file(message):
    """The content and MIME type of the file of a message that carries one."""
    saved = MessageFile.objects.filter(message=message).first()
    if saved is not None and default_storage.exists(saved.path):
        with default_storage.open(saved.path) as stored:
            return stored.read(), saved.mime_type

    try:
        downloaded = download_attachment(message)
    except AttachmentUnavailable as exc:
        logger.warning("File of message %s not available: HTTP %s", message.pk, exc.status_code)
        # Only "not found" means the file is gone. A refused token, a rate limit or no answer at all
        # say nothing about the file, so those can be tried again once the cause is fixed
        if exc.status_code in (404, 410):
            raise FileGone from exc
        raise FileNotReached from exc
    if downloaded.size > settings.MESSAGE_FILE_MAX_BYTES:
        raise FileTooLarge
    mime_type = downloaded.mime_type or "application/octet-stream"
    # One name per message, replacing whatever is there: a leftover or a second opening at the
    # same time must not leave a file that no record points to (the cleanup would never find it)
    name = f"message-files/{message.pk}"
    default_storage.delete(name)
    if saved is not None:
        default_storage.delete(saved.path)
    path = default_storage.save(name, ContentFile(downloaded.content))
    MessageFile.objects.update_or_create(
        message=message,
        defaults={"path": path, "mime_type": mime_type, "size": downloaded.size},
    )
    return downloaded.content, mime_type
