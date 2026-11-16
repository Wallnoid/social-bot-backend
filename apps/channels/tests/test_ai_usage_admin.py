"""
The Django admin shows the Social Bot team how much AI each business used: by day, model and who
pays, with the total of what is filtered. It is for reading only.
"""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.channels.models import AIUsage
from apps.tenants.models import Tenant

User = get_user_model()


@pytest.fixture
def staff_client(client, db):
    client.force_login(
        User.objects.create_superuser(
            email="staff@example.com", password="staffpass123", first_name="S", last_name="U"
        )
    )
    return client


@pytest.fixture
def usage(db):
    acme = Tenant.objects.create(name="Acme Dental")
    rival = Tenant.objects.create(name="Rival Clinic")

    def row(tenant, day, model, paid_by, calls, input_tokens, output_tokens, thinking_tokens):
        return AIUsage.objects.create(
            tenant=tenant,
            day=day,
            model=model,
            paid_by=paid_by,
            calls=calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
        )

    row(acme, date(2026, 11, 10), "gemini-a", "platform", 10, 1000, 200, 30)
    row(acme, date(2026, 11, 11), "gemini-a", "platform", 5, 500, 100, 10)
    row(acme, date(2026, 11, 11), "gemini-a", "business", 7, 700, 70, 7)
    row(rival, date(2026, 11, 11), "gemini-a", "platform", 100, 9000, 900, 90)
    return acme, rival


def changelist(client, **filters):
    return client.get(reverse("admin:channels_aiusage_changelist"), filters)


def test_the_admin_lists_the_usage_and_totals_all_of_it(staff_client, usage):
    response = changelist(staff_client)

    assert response.status_code == 200
    assert len(response.context["cl"].result_list) == 4
    assert response.context["totals"] == {
        "calls": 122,
        "input_tokens": 11200,
        "output_tokens": 1270,
        "thinking_tokens": 137,
        "cached_tokens": 0,
    }


def test_the_total_is_the_one_of_the_filtered_business_range_and_payer(staff_client, usage):
    acme, _ = usage

    response = changelist(
        staff_client,
        tenant__id__exact=acme.pk,
        day__gte="2026-11-11",
        paid_by__exact="platform",
    )

    assert len(response.context["cl"].result_list) == 1
    assert response.context["totals"] == {
        "calls": 5,
        "input_tokens": 500,
        "output_tokens": 100,
        "thinking_tokens": 10,
        "cached_tokens": 0,
    }


def test_the_usage_is_read_only(staff_client, usage):
    row = AIUsage.objects.first()

    assert staff_client.get(reverse("admin:channels_aiusage_add")).status_code == 403
    assert (
        staff_client.post(
            reverse("admin:channels_aiusage_delete", args=[row.pk]), {"post": "yes"}
        ).status_code
        == 403
    )
    change = staff_client.post(
        reverse("admin:channels_aiusage_change", args=[row.pk]), {"calls": 999}
    )
    assert change.status_code in (200, 403)
    row.refresh_from_db()
    assert row.calls != 999


def test_the_page_shows_the_total_of_what_is_filtered_above_the_list(staff_client, usage):
    acme, _ = usage

    page = changelist(staff_client, tenant__id__exact=acme.pk, paid_by__exact="platform")

    content = page.content.decode()
    assert "Total of what is shown" in content
    # 10 + 5 calls, 1,500 input, 300 output and 40 thinking tokens of the two days of Acme
    expected_texts = (
        "15 calls",
        "1500 input tokens",
        "0 of them from the cache",
        "300 output tokens",
        "40 thinking tokens",
    )
    for expected in expected_texts:
        assert expected in content
