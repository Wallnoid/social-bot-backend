"""
Custom throttling classes for rate limiting.
"""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class BurstAnonRateThrottle(AnonRateThrottle):
    """
    Rate limit for anonymous users making burst requests.
    Useful for login endpoints to prevent brute force.
    """

    scope = "burst_anon"
    rate = "5/minute"


class BurstUserRateThrottle(UserRateThrottle):
    """
    Rate limit for authenticated users making burst requests.
    Useful for sensitive operations like password changes.
    """

    scope = "burst_user"
    rate = "10/minute"


class SustainedAnonRateThrottle(AnonRateThrottle):
    """
    Sustained rate limit for anonymous users.
    """

    scope = "sustained_anon"
    rate = "100/hour"


class SustainedUserRateThrottle(UserRateThrottle):
    """
    Sustained rate limit for authenticated users.
    """

    scope = "sustained_user"
    rate = "1000/hour"


class ToolTryRateThrottle(UserRateThrottle):
    """Tries of the tools of the bot: an admin tries a few, but nobody scans addresses with them."""

    scope = "tool_try"
    rate = "10/minute"
