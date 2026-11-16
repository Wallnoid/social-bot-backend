"""
How much AI each business uses each day, for billing. The wrapper of the AI provider adds every
call that answered; the Django admin shows the numbers. Recording must never stop the bot.
"""

import logging

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .bot_context import business_zone
from .models import AIUsage, ChannelAccount

logger = logging.getLogger(__name__)

# What Gemini reports about a call, in the order the row keeps it. The cached tokens are a part of
# the input that the provider charges less for
USAGE_FIELDS = {
    "input_tokens": "prompt_token_count",
    "output_tokens": "candidates_token_count",
    "thinking_tokens": "thoughts_token_count",
    "cached_tokens": "cached_content_token_count",
}
MODEL_MAX_LENGTH = AIUsage._meta.get_field("model").max_length


def tokens_of(response) -> dict:
    """The tokens a response reports, zeros for what it does not report."""
    usage = getattr(getattr(response, "raw", None), "usage_metadata", None)
    if usage is None:
        # Only the Gemini way is known: another provider would be billed nothing without notice
        logger.warning("An answer of the AI reported no usage: it counts with zero tokens.")
    return {field: int(getattr(usage, name, 0) or 0) for field, name in USAGE_FIELDS.items()}


def tenant_of(account):
    """The business of the account, or None when the account has no business."""
    return (
        ChannelAccount.objects.filter(account=account).values_list("tenant_id", flat=True).first()
    )


def record_usage(account, tenant_id, model: str, response) -> None:
    """Add one call that answered to the day of the business. Never raises."""
    try:
        add_usage(account, tenant_id, model, tokens_of(response))
    except Exception:
        logger.exception(
            "Could not record the AI usage of account %s", getattr(account, "pk", None)
        )


def add_usage(account, tenant_id, model: str, tokens: dict) -> None:
    if tenant_id is None:
        return
    day = timezone.now().astimezone(business_zone()).date()
    paid_by = AIUsage.PaidBy.BUSINESS if account.ai_api_key else AIUsage.PaidBy.PLATFORM
    key = {
        "tenant_id": tenant_id,
        "day": day,
        "model": (model or "")[:MODEL_MAX_LENGTH],
        "paid_by": paid_by,
    }
    add = {"calls": F("calls") + 1, **{field: F(field) + value for field, value in tokens.items()}}
    # An increment in the database, so two calls at the same time never lose one
    if AIUsage.objects.filter(**key).update(**add):
        return
    try:
        # In its own savepoint: losing the race must not break the transaction of the bot
        with transaction.atomic():
            AIUsage.objects.create(**key, calls=1, **tokens)
    except IntegrityError:
        # Another call created the row first
        AIUsage.objects.filter(**key).update(**add)
