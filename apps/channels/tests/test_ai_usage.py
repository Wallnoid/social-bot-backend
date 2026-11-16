"""
How much AI each business uses each day, for billing: calls and tokens by day, model and who pays
(the platform or the own key of the account). The AI is a scripted fake that reports its usage the
way Gemini does.
"""

from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from wanps.ai.types import AIResponse

from apps.channels.models import AIUsage
from apps.channels.tests.test_bot_context import bot_account, writes
from apps.channels.tests.test_tool_calls import ScriptedAI, asks_for

pytestmark = pytest.mark.usefixtures("inline_processing_and_platform_ai", "no_real_meta_profiles")


def used(prompt, candidates, thoughts=0):
    """What Gemini reports about one call."""
    return SimpleNamespace(
        prompt_token_count=prompt,
        candidates_token_count=candidates,
        thoughts_token_count=thoughts,
    )


def answer(text="Hello!", usage=None):
    return AIResponse(content=text, raw=SimpleNamespace(usage_metadata=usage))


def tool_call(usage=None):
    response = asks_for("get_client_info")
    response.raw = SimpleNamespace(usage_metadata=usage)
    return response


class MeteredAI(ScriptedAI):
    """The scripted AI, with a model name like a real provider."""

    model = "gemini-test"


def today():
    from django.conf import settings
    from django.utils import timezone

    return timezone.now().astimezone(ZoneInfo(settings.BUSINESS_TIME_ZONE)).date()


@pytest.fixture
def link(admin_client, tenant, meta_app):
    return bot_account(admin_client, tenant, meta_app)


def test_an_answer_adds_one_call_and_its_tokens_to_the_day_of_the_business(
    client, meta_app, link, tenant
):
    ai = MeteredAI(answer(usage=used(prompt=1000, candidates=200, thoughts=50)))

    writes(client, meta_app, ai)

    row = AIUsage.objects.get()
    assert (row.tenant_id, row.day, row.model, row.paid_by) == (
        tenant.pk,
        today(),
        "gemini-test",
        "platform",
    )
    assert (row.calls, row.input_tokens, row.output_tokens, row.thinking_tokens) == (
        1,
        1000,
        200,
        50,
    )


def test_a_turn_with_tools_adds_each_call(client, meta_app, link):
    ai = MeteredAI(
        tool_call(usage=used(prompt=500, candidates=10)),
        answer(usage=used(prompt=700, candidates=40, thoughts=5)),
    )

    writes(client, meta_app, ai)

    row = AIUsage.objects.get()
    assert (row.calls, row.input_tokens, row.output_tokens, row.thinking_tokens) == (2, 1200, 50, 5)


def test_an_answer_with_no_usage_counts_the_call_with_zero_tokens(client, meta_app, link):
    ai = MeteredAI(answer(usage=None))

    writes(client, meta_app, ai)

    row = AIUsage.objects.get()
    assert (row.calls, row.input_tokens, row.output_tokens, row.thinking_tokens) == (1, 0, 0, 0)


def test_a_call_that_fails_is_not_counted(client, meta_app, link):
    class BrokenAI(MeteredAI):
        def generate(self, *args, **kwargs):
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

    with mock.patch("apps.channels.failures.retry_bot_reply.apply_async"):
        writes(client, meta_app, BrokenAI())

    assert AIUsage.objects.count() == 0


def test_days_models_and_businesses_are_kept_apart(client, meta_app, link, tenant):
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    from django.conf import settings
    from django.utils import timezone

    from apps.channels.tests.test_manage_accounts import add_account
    from apps.tenants.models import Tenant

    class OtherModelAI(MeteredAI):
        model = "gemini-other"

    rival = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "222")
    yesterday = timezone.now() - timedelta(days=1)

    writes(client, meta_app, MeteredAI(answer(usage=used(10, 1))), message_id="m1")
    writes(client, meta_app, OtherModelAI(answer(usage=used(20, 2))), message_id="m2")
    with mock.patch("django.utils.timezone.now", return_value=yesterday):
        writes(client, meta_app, MeteredAI(answer(usage=used(40, 4))), message_id="m3")

    zone = ZoneInfo(settings.BUSINESS_TIME_ZONE)
    rows = {
        (row.day, row.model): (row.calls, row.input_tokens)
        for row in AIUsage.objects.filter(tenant=tenant)
    }
    assert rows == {
        (today(), "gemini-test"): (1, 10),
        (today(), "gemini-other"): (1, 20),
        (yesterday.astimezone(zone).date(), "gemini-test"): (1, 40),
    }
    assert not AIUsage.objects.filter(tenant=rival.tenant).exists()


def test_a_call_with_the_own_key_of_the_account_is_recorded_apart_from_the_platform_one(
    client, meta_app, link
):
    writes(client, meta_app, MeteredAI(answer(usage=used(10, 1))), message_id="m1")
    link.account.ai_api_key = "key-of-the-business"
    link.account.save(update_fields=["ai_api_key"])
    writes(client, meta_app, MeteredAI(answer(usage=used(30, 3))), message_id="m2")

    rows = {row.paid_by: (row.calls, row.input_tokens) for row in AIUsage.objects.all()}
    assert rows == {"platform": (1, 10), "business": (1, 30)}


def test_an_error_while_recording_never_stops_the_bot(client, meta_app, link):
    ai = MeteredAI(answer("Still answers.", usage=used(10, 1)))

    with mock.patch("apps.channels.usage.add_usage", side_effect=RuntimeError("database down")):
        post = writes(client, meta_app, ai)

    sent = [c.kwargs["json"] for c in post.call_args_list if "text" in c.kwargs["json"]]
    assert [m["text"]["body"] for m in sent] == ["Still answers."]
    assert AIUsage.objects.count() == 0


def test_the_tokens_served_from_the_cache_are_kept_apart_inside_the_input(client, meta_app, link):
    usage = used(prompt=10000, candidates=100)
    usage.cached_content_token_count = 8000
    ai = MeteredAI(answer(usage=usage))

    writes(client, meta_app, ai)

    row = AIUsage.objects.get()
    assert (row.input_tokens, row.cached_tokens) == (10000, 8000)


def test_two_calls_creating_the_row_of_the_day_at_once_both_count_and_the_bot_answers(
    client, meta_app, link, tenant
):
    from django.db.models.query import QuerySet

    # Another call created the row of the day between our update and our insert
    AIUsage.objects.create(
        tenant=tenant, day=today(), model="gemini-test", paid_by="platform", calls=1
    )
    original = QuerySet.update
    seen = []

    def first_finds_nothing(queryset, **kwargs):
        if queryset.model is AIUsage and not seen:
            seen.append(True)
            return 0
        return original(queryset, **kwargs)

    with mock.patch.object(QuerySet, "update", first_finds_nothing):
        post = writes(client, meta_app, MeteredAI(answer("Hi there.", usage=used(10, 1))))

    sent = [c.kwargs["json"] for c in post.call_args_list if "text" in c.kwargs["json"]]
    assert [m["text"]["body"] for m in sent] == ["Hi there."]
    assert AIUsage.objects.get().calls == 2


def test_a_model_with_a_very_long_name_is_still_recorded(client, meta_app, link):
    class LongNameAI(MeteredAI):
        model = "models/" + "x" * 150

    writes(client, meta_app, LongNameAI(answer(usage=used(10, 1))))

    row = AIUsage.objects.get()
    assert row.calls == 1 and row.model.startswith("models/xxx") and len(row.model) <= 100


def test_an_answer_with_no_usage_is_told_in_the_log(client, meta_app, link, caplog):
    writes(client, meta_app, MeteredAI(answer(usage=None)))

    assert "reported no usage" in caplog.text
