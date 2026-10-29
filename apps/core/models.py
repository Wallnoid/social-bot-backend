"""
Core abstract models.

These base models provide common fields and behavior (timestamps, soft delete,
UUID primary keys) that all other models in the project should inherit from.
"""

import uuid

from django.db import models
from django.utils import timezone


class SoftDeleteManager(models.Manager):
    """Manager that excludes soft-deleted objects by default."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    """Manager that includes all objects, even soft-deleted ones."""

    pass


class TimeStampedModel(models.Model):
    """
    Abstract model that provides self-updating 'created_at' and 'updated_at' fields.
    """

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when this object was created.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when this object was last updated.",
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class SoftDeleteModel(models.Model):
    """
    Abstract model that provides soft delete functionality.

    Instead of permanently deleting objects from the database,
    they are marked as deleted with a timestamp.

    Usage:
        obj.soft_delete()   # Mark as deleted
        obj.restore()       # Restore a soft-deleted object
        Model.objects.all() # Returns only non-deleted objects
        Model.all_objects.all() # Returns ALL objects, including deleted
    """

    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this object has been soft-deleted.",
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when this object was soft-deleted.",
    )

    # Default manager excludes soft-deleted objects
    objects = SoftDeleteManager()
    # Manager that includes all objects
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def soft_delete(self):
        """Mark this object as deleted."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    def restore(self):
        """Restore a soft-deleted object."""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    def hard_delete(self):
        """Permanently delete this object from the database."""
        super().delete()

    def delete(self, using=None, keep_parents=False):
        """Override delete to perform soft delete by default."""
        self.soft_delete()


class BaseModel(TimeStampedModel, SoftDeleteModel):
    """
    Base model for all project models.

    Provides:
    - UUID primary key
    - created_at / updated_at timestamps
    - Soft delete (is_deleted / deleted_at)

    Usage:
        class MyModel(BaseModel):
            name = models.CharField(max_length=255)
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for this object.",
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]
