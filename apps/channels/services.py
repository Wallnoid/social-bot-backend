"""
Rules shared by the API and the Django admin when a business's account is disconnected.
"""


def disconnect(link):
    """
    Disconnect the account of a link (call inside a transaction).

    The wanps-core account stays, because its messages reference it: it is archived.
    The webhook finds accounts by channel and id even when inactive, so the id is
    freed (its events are ignored and the same number can be connected again) but
    kept readable, cut to fit the 64 characters of the field.
    """
    account = link.account
    account.is_active = False
    account.access_token = ""
    account.ai_api_key = ""
    account.external_id = f"{account.external_id[:40]}#disconnected-{account.pk}"
    account.save(
        update_fields=["is_active", "access_token", "ai_api_key", "external_id", "updated_at"]
    )
    link.soft_delete()
