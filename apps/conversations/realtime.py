"""
The inbox in real time: the permit to open the permanent connection.

The browser cannot send its headers when it opens a WebSocket, and the access token must not
travel in the address (it would be logged), so it first asks the API for a permit that works
once and for a few seconds, and opens the connection with that.
"""

import secrets

from django.conf import settings
from django.core.cache import caches


def _permits():
    return caches["ws_tickets"]


def issue_ticket(user_id, tenant_id) -> str:
    """A permit for this user to connect as a member of this business."""
    ticket = secrets.token_urlsafe(32)
    _permits().set(
        f"ws-ticket:{ticket}", (str(user_id), str(tenant_id)), settings.WS_TICKET_TIMEOUT
    )
    return ticket


def redeem_ticket(ticket: str):
    """The (user id, business id) a permit was issued for, or None. A permit works only once."""
    key = f"ws-ticket:{ticket}"
    holder = _permits().get(key)
    # Of two connections trying the same permit, only the one that deletes it gets in
    if holder is None or not _permits().delete(key):
        return None
    return holder


def group_of(tenant_id) -> str:
    """The group that every connected member of a business belongs to."""
    return f"tenant.{tenant_id}"
