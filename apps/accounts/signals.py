"""
Signals for the accounts app.

Django signals allow decoupled applications to get notified
when certain actions occur. This module handles user-related signals.
"""

import logging

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

User = get_user_model()


@receiver(post_save, sender=User)
def user_post_save(sender, instance, created, **kwargs):
    """
    Signal handler for User post_save.

    Triggered when a user is created or updated.
    Use this to:
    - Send welcome emails
    - Create related profiles
    - Initialize user settings
    - Log user creation
    """
    if created:
        logger.info(
            "New user created: %s (id=%s)",
            instance.email,
            instance.id,
        )
        # Example: Send welcome email
        # send_welcome_email.delay(instance.id)

        # Example: Create user profile/settings
        # UserProfile.objects.create(user=instance)
