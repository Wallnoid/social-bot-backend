"""
Shared utility functions for the project.
"""

import random
import string
import uuid

from django.utils.text import slugify


def generate_unique_slug(model_class, value, slug_field="slug"):
    """
    Generate a unique slug for a model instance.

    If the slug already exists, appends a random suffix.

    Args:
        model_class: The Django model class.
        value: The string to slugify.
        slug_field: The name of the slug field (default: 'slug').

    Returns:
        A unique slug string.

    Example:
        slug = generate_unique_slug(Article, "My Article Title")
        # Returns "my-article-title" or "my-article-title-a3b2" if duplicate
    """
    slug = slugify(value)
    unique_slug = slug
    counter = 1

    while model_class.objects.filter(**{slug_field: unique_slug}).exists():
        suffix = _random_string(4)
        unique_slug = f"{slug}-{suffix}"
        counter += 1

        # Safety valve
        if counter > 100:
            unique_slug = f"{slug}-{uuid.uuid4().hex[:8]}"
            break

    return unique_slug


def generate_code(length=6, chars=string.ascii_uppercase + string.digits):
    """
    Generate a random alphanumeric code.

    Args:
        length: Length of the code (default: 6).
        chars: Characters to use (default: uppercase + digits).

    Returns:
        A random code string (e.g., "A3B2C1").
    """
    return "".join(random.choices(chars, k=length))


def generate_numeric_code(length=6):
    """
    Generate a random numeric code (e.g., for OTP).

    Args:
        length: Length of the code (default: 6).

    Returns:
        A random numeric string (e.g., "482917").
    """
    return "".join(random.choices(string.digits, k=length))


def _random_string(length=4):
    """Generate a short random lowercase string."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def get_client_ip(request):
    """
    Extract the client's IP address from the request.

    Handles X-Forwarded-For header for reverse proxy setups.

    Args:
        request: The Django HTTP request.

    Returns:
        The client's IP address as a string.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")
