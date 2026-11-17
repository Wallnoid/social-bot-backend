"""
A state of the bot kept for each chat (a row per account and client): the inbox reads it for a page
of chats at once, or for one chat.
"""


def per_chat(rows, chats, field: str) -> dict:
    """The `field` of the rows of the chats, in one query, as {(account, client): value}."""
    found = rows.filter(
        account_id__in={chat["account"]["id"] for chat in chats},
        contact_id__in={chat["contact_id"] for chat in chats},
    )
    return {(row.account_id, row.contact_id): getattr(row, field) for row in found}


def of_chat(rows, account, contact_id, field: str):
    """The `field` of the row of one chat, or None when it has none."""
    return per_chat(rows, [{"account": {"id": account.pk}, "contact_id": contact_id}], field).get(
        (account.pk, contact_id)
    )
