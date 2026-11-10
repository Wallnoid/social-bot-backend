"""
Background jobs of the accounts app.
"""

import logging

from celery import shared_task
from django.contrib.auth import get_user_model

from .emails import send_password_reset_email

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def send_password_reset_email_to(email: str) -> None:
    """
    Email a reset link if an active account uses this email. Runs in the background
    so the request answers the same, and as fast, whether the account exists or not.
    """
    user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
    if user is None:
        return
    try:
        send_password_reset_email(user)
    except Exception:
        logger.exception("Could not send password reset email to %s", user.pk)
