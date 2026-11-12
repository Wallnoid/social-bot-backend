"""
Tests for a business admin turning the bot of an account on or off and writing its instructions.
"""

import json

import pytest
from drf_spectacular.generators import SchemaGenerator
from wanps.messaging.models import Account, App

from apps.channels.tests.test_manage_accounts import (
    ACCOUNTS_URL,
    TOKEN,
    add_account,
    detail_url,
)
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

INSTRUCTIONS = "You are the assistant of Acme Dental. Answer briefly."


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def admin_client(tenant):
    return client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


@pytest.fixture(autouse=True)
def platform_ai(settings, monkeypatch):
    """The AI of the platform, so no test depends on what the `.env` of the machine says."""
    settings.WANPS_AI = {"PROVIDER": "gemini", "API_KEY": "platform-key"}
    # Only the Gemini SDK is installed in the image, whatever the machine running the tests has
    monkeypatch.setattr(
        "apps.channels.serializers.provider_is_installed",
        lambda provider: provider == "gemini",
        raising=False,
    )


def turn_on(api, link, **extra):
    body = {"is_active": True, "instructions": INSTRUCTIONS, **extra}
    return api.patch(detail_url(link), body, format="json")


def stored(link):
    return Account.objects.get(pk=link.account_id)


def test_admin_turns_the_bot_on_with_instructions(admin_client, tenant, meta_app):
    link = add_account(tenant, meta_app, "111")

    response = turn_on(admin_client, link)

    assert response.status_code == 200
    assert response.data["data"]["is_active"] is True
    assert (stored(link).is_active, stored(link).system_prompt) == (True, INSTRUCTIONS)


def test_admin_turns_the_bot_off_and_the_instructions_stay(admin_client, tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    turn_on(admin_client, link)

    response = admin_client.patch(detail_url(link), {"is_active": False}, format="json")

    assert response.status_code == 200
    assert response.data["data"]["is_active"] is False
    assert (stored(link).is_active, stored(link).system_prompt) == (False, INSTRUCTIONS)


@pytest.mark.parametrize("role", [Membership.Role.AGENT, Membership.Role.SUPERVISOR])
def test_agents_and_supervisors_cannot_turn_the_bot_on_or_off_or_write_instructions(
    tenant, meta_app, role
):
    link = add_account(tenant, meta_app, "111")
    member = client_for(add_member(tenant, "member@acme.test", role))

    response = turn_on(member, link)

    assert response.status_code == 403
    assert (stored(link).is_active, stored(link).system_prompt) == (False, "")


def test_an_account_of_another_business_is_not_found_when_turning_the_bot_on(
    admin_client, meta_app
):
    rival = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "222")

    response = turn_on(admin_client, rival)

    assert response.status_code == 404
    assert (stored(rival).is_active, stored(rival).system_prompt) == (False, "")


@pytest.mark.parametrize("instructions", [None, "", "   "])
def test_turning_the_bot_on_without_instructions_is_refused_and_it_stays_off(
    admin_client, tenant, meta_app, instructions
):
    link = add_account(tenant, meta_app, "111")
    body = {"is_active": True}
    if instructions is not None:
        body["instructions"] = instructions

    response = admin_client.patch(detail_url(link), body, format="json")

    assert response.status_code == 400
    assert "instructions" in response.data["errors"]
    assert stored(link).is_active is False


def test_turning_the_bot_on_without_any_ai_is_refused_and_it_stays_off(
    admin_client, tenant, meta_app, settings
):
    settings.WANPS_AI = {}
    link = add_account(tenant, meta_app, "111")

    response = turn_on(admin_client, link)

    assert response.status_code == 400
    assert "is_active" in response.data["errors"]
    assert stored(link).is_active is False


def test_an_account_with_its_own_ai_can_be_turned_on_even_if_the_platform_has_none(
    admin_client, tenant, meta_app, settings
):
    settings.WANPS_AI = {}
    link = add_account(tenant, meta_app, "111")
    account = stored(link)
    account.ai_provider, account.ai_api_key = "gemini", "own-key"
    account.save()

    response = turn_on(admin_client, link)

    assert response.status_code == 200
    assert stored(link).is_active is True


def test_the_instructions_cannot_be_emptied_while_the_bot_is_on(admin_client, tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    turn_on(admin_client, link)

    response = admin_client.patch(detail_url(link), {"instructions": ""}, format="json")

    assert response.status_code == 400
    assert "instructions" in response.data["errors"]
    assert stored(link).system_prompt == INSTRUCTIONS


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_member_sees_if_the_bot_is_on_and_its_instructions(tenant, meta_app, role):
    link = add_account(tenant, meta_app, "111")
    Account.objects.filter(pk=link.account_id).update(is_active=True, system_prompt=INSTRUCTIONS)
    member = client_for(add_member(tenant, "member@acme.test", role))

    response = member.get(ACCOUNTS_URL)

    assert response.status_code == 200
    (account,) = response.data["data"]
    assert (account["is_active"], account["instructions"]) == (True, INSTRUCTIONS)


def test_reading_an_account_never_shows_the_token_or_an_ai_key(admin_client, tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    account = stored(link)
    account.ai_provider, account.ai_api_key = "gemini", "own-key-never-shown"
    account.save()

    listed = admin_client.get(ACCOUNTS_URL)
    edited = turn_on(admin_client, link)

    for response in (listed, edited):
        assert response.status_code == 200
        text = response.content.decode()
        assert TOKEN not in text and "own-key-never-shown" not in text
        assert "access_token" not in text and "ai_api_key" not in text


def test_the_api_docs_describe_the_bot_fields_without_any_ai_key():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema["components"]["schemas"]

    edit = components["PatchedUpdateAccountRequest"]["properties"]
    assert edit["is_active"]["type"] == "boolean"
    assert edit["instructions"]["type"] == "string"
    shown = components["ChannelAccount"]["properties"]
    assert shown["is_active"]["type"] == "boolean"
    assert shown["instructions"]["type"] == "string"
    for name in ("ChannelAccount", "PatchedUpdateAccountRequest"):
        assert "ai_api_key" not in json.dumps(components[name])


def test_a_provider_whose_sdk_is_not_installed_cannot_be_turned_on(
    admin_client, tenant, meta_app, settings
):
    settings.WANPS_AI = {}
    link = add_account(tenant, meta_app, "111")
    account = stored(link)
    account.ai_provider, account.ai_api_key = "openai", "own-key"
    account.save()

    response = turn_on(admin_client, link)

    assert response.status_code == 400
    assert "is_active" in response.data["errors"]
    assert stored(link).is_active is False


def test_the_instructions_have_a_maximum_length(admin_client, tenant, meta_app):
    link = add_account(tenant, meta_app, "111")

    too_long = turn_on(admin_client, link, instructions="x" * 10001)
    just_enough = turn_on(admin_client, link, instructions="x" * 10000)

    assert too_long.status_code == 400
    assert "instructions" in too_long.data["errors"]
    assert just_enough.status_code == 200


def test_the_ai_of_an_account_cannot_be_changed_through_the_api(admin_client, tenant, meta_app):
    link = add_account(tenant, meta_app, "111")

    response = admin_client.patch(
        detail_url(link),
        {"ai_provider": "openai", "ai_model": "m", "ai_api_key": "k", "ai_level": 3},
        format="json",
    )

    assert response.status_code == 200
    account = stored(link)
    assert (account.ai_provider, account.ai_model, account.ai_api_key) == ("", "", "")
    assert account.ai_level == 1
