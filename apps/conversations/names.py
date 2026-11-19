"""
How a chat names its client and its account: the inbox, its events and the contacts show the same.
"""

# What a chat shows while Meta has not given the name of the client (shown, never saved)
GENERIC_NAMES = {"messenger": "Messenger user", "instagram": "Instagram user"}


def display_name(channel: str, name: str) -> str:
    """The name of the client, or the generic one of Messenger and Instagram.

    WhatsApp keeps an empty name empty: the id of the client is the phone, and the frontend
    shows it.
    """
    return name or GENERIC_NAMES.get(channel, "")


def account_of(link) -> dict:
    """How the inbox names an account: with the id the list of accounts shows."""
    return {"id": link.id, "name": link.account.name, "channel": link.account.channel}
