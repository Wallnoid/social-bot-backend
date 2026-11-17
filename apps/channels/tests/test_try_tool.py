"""
A business admin tries a tool of the bot with sample values before turning it on: the very same call
the bot makes runs, and the admin sees whether it worked. The network is a fake.
"""

import pytest
from django.core.cache import cache
from wanps.messaging.models import App

from apps.channels.models import ChannelTool, ToolCall
from apps.channels.tests.test_manage_accounts import add_account
from apps.channels.tests.test_safe_http import PUBLIC, answer, network
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

SECRET = "tool-secret-never-shown"
NAMES = {"api.acme.example": [PUBLIC]}


@pytest.fixture(autouse=True)
def fresh_limits(settings):
    cache.clear()  # the counters of the throttles live in the cache
    settings.TOOL_CALL_TIMEOUT = 5
    settings.TOOL_CALL_MAX_BYTES = 5000


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def admin_client(tenant):
    return client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


@pytest.fixture
def link(tenant, meta_app):
    return add_account(tenant, meta_app, "111")


def add_tool(link, **overrides):
    values = {
        "account": link.account,
        "name": "opening_hours",
        "description": "Gives the opening hours of the clinic for a day.",
        "url": "https://api.acme.example/hours",
        "parameters": [
            {"name": "day", "type": "string", "description": "Day of the week", "required": True}
        ],
        "auth_type": ChannelTool.AuthType.BEARER,
        "auth_secret": SECRET,
        "is_active": True,
    }
    return ChannelTool.objects.create(**{**values, **overrides})


def try_url(link, tool):
    return f"/api/v1/channels/accounts/{link.id}/tools/{tool.id}/try/"


def try_it(api, link, tool, values=None):
    return api.post(
        try_url(link, tool),
        {"values": {"day": "monday"} if values is None else values},
        format="json",
    )


def test_a_successful_try_shows_the_status_and_the_beginning_of_the_answer(admin_client, link):
    tool = add_tool(link)

    with network(answer(200, b'{"open": "09:00-18:00"}'), names=NAMES):
        response = try_it(admin_client, link, tool)

    assert response.status_code == 200
    assert response.data["data"] == {
        "ok": True,
        "http_status": 200,
        "body": '{"open": "09:00-18:00"}',
        "truncated": False,
        "error": None,
    }


def test_the_try_sends_the_same_request_the_bot_would_send(admin_client, link):
    tool = add_tool(link)

    with network(answer(200, b"{}"), names=NAMES) as wire:
        try_it(admin_client, link, tool, {"day": "monday", "ignored": "not declared"})

    request = wire.requests[0]
    assert request.url.endswith("/hours?day=monday")
    assert request.headers["Authorization"] == f"Bearer {SECRET}"
    assert request.headers["Host"] == "api.acme.example"


@pytest.mark.parametrize(
    "given, code",
    [
        (answer(404, b"nothing here"), "http_error"),
        (answer(500, b"broken"), "http_error"),
        (answer(200, b"x" * 6000), "too_large"),
    ],
)
def test_a_failure_of_the_call_is_shown_with_its_code_and_the_status(
    admin_client, link, given, code
):
    tool = add_tool(link)

    with network(given, names=NAMES):
        response = try_it(admin_client, link, tool)

    assert response.status_code == 200
    data = response.data["data"]
    assert (data["ok"], data["error"], data["body"]) == (False, code, None)
    assert data["http_status"] == given.status_code or code == "too_large"


def test_an_address_that_is_not_public_is_blocked_and_the_try_says_so(admin_client, link):
    tool = add_tool(link, url="https://internal.acme.example/hours")

    with network(names={"internal.acme.example": ["10.0.0.5"]}):
        response = try_it(admin_client, link, tool)

    data = response.data["data"]
    assert (data["ok"], data["error"], data["http_status"]) == (False, "blocked", None)


def test_a_host_that_does_not_exist_or_does_not_answer_is_unreachable(admin_client, link):
    import requests

    tool = add_tool(link)

    with network(requests.ConnectionError("down"), names=NAMES):
        refused = try_it(admin_client, link, tool)
    gone = add_tool(link, name="gone", url="https://gone.acme.example/x")
    with network(names=NAMES):
        unknown = try_it(admin_client, link, gone)

    assert refused.data["data"]["error"] == "unreachable"
    assert unknown.data["data"]["error"] == "unreachable"


def test_a_call_that_takes_too_long_is_shown_as_a_timeout(admin_client, link):
    import requests

    tool = add_tool(link)

    with network(requests.Timeout("slow"), names=NAMES):
        response = try_it(admin_client, link, tool)

    assert response.data["data"]["error"] == "timeout"


@pytest.mark.parametrize(
    "values, reason",
    [
        ({}, "Missing required value: day"),
        ({"day": ""}, "Missing required value: day"),
        ({"day": ["monday"]}, "Wrong type of value: day"),
    ],
)
def test_values_that_are_missing_or_of_the_wrong_type_are_refused_with_the_reason(
    admin_client, link, values, reason
):
    tool = add_tool(link)

    with network(names=NAMES) as wire:
        response = try_it(admin_client, link, tool, values)

    assert response.status_code == 400
    assert reason in str(response.data)
    assert wire.requests == []  # nothing was sent


def test_the_key_is_hidden_in_the_result_even_if_the_endpoint_sends_it_back(admin_client, link):
    tool = add_tool(link)
    echo = f'{{"authorization": "Bearer {SECRET}", "again": "{SECRET}"}}'.encode()

    with network(answer(200, echo), names=NAMES):
        response = try_it(admin_client, link, tool)

    assert SECRET not in str(response.data) and SECRET not in response.content.decode()
    assert response.data["data"]["body"].count("[hidden]") == 2


def test_the_answer_is_cut_at_2000_characters(admin_client, link):
    tool = add_tool(link)

    with network(answer(200, b"a" * 3000), names=NAMES):
        response = try_it(admin_client, link, tool)

    data = response.data["data"]
    assert (len(data["body"]), data["truncated"]) == (2000, True)


def test_a_tool_that_is_off_can_be_tried(admin_client, link):
    tool = add_tool(link, is_active=False)

    with network(answer(200, b"{}"), names=NAMES):
        response = try_it(admin_client, link, tool)

    assert response.data["data"]["ok"] is True


def test_the_try_is_kept_in_the_record_of_calls(admin_client, link):
    tool = add_tool(link)

    with network(answer(200, b"{}"), answer(404, b"no"), names=NAMES):
        try_it(admin_client, link, tool)
        try_it(admin_client, link, tool)

    calls = ToolCall.objects.filter(account=link.account, tool="opening_hours").order_by("id")
    assert [(call.status, call.http_status, call.host) for call in calls] == [
        ("ok", 200, "api.acme.example"),
        ("http_error", 404, "api.acme.example"),
    ]


def test_no_secret_is_kept_in_the_record_of_calls(admin_client, link):
    tool = add_tool(link)

    with network(answer(200, SECRET.encode()), names=NAMES):
        try_it(admin_client, link, tool)

    call = ToolCall.objects.get(account=link.account)
    assert SECRET not in str(vars(call))


@pytest.mark.parametrize("role", [Membership.Role.AGENT, Membership.Role.SUPERVISOR])
def test_only_an_admin_of_the_business_can_try_its_tools(tenant, link, role):
    tool = add_tool(link)
    member = client_for(add_member(tenant, f"{role}@acme.test", role))

    with network(answer(200, b"{}"), names=NAMES) as wire:
        response = try_it(member, link, tool)

    assert response.status_code == 403
    assert wire.requests == []


def test_the_tools_of_another_business_or_a_made_up_tool_are_not_found(
    admin_client, link, meta_app
):
    import uuid

    rival = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "222")
    rival_tool = add_tool(rival)
    tool = add_tool(link)

    with network(answer(200, b"{}"), names=NAMES) as wire:
        other_business = admin_client.post(
            try_url(rival, rival_tool), {"values": {"day": "x"}}, format="json"
        )
        crossed = admin_client.post(
            try_url(link, rival_tool), {"values": {"day": "x"}}, format="json"
        )
        made_up = admin_client.post(
            f"/api/v1/channels/accounts/{link.id}/tools/{uuid.uuid4()}/try/",
            {"values": {"day": "x"}},
            format="json",
        )

    assert (other_business.status_code, crossed.status_code, made_up.status_code) == (404, 404, 404)
    assert wire.requests == []
    assert tool.pk is not None


def test_after_10_tries_in_a_minute_the_next_one_is_refused(admin_client, link):
    tool = add_tool(link)

    with network(*[answer(200, b"{}")] * 11, names=NAMES) as wire:
        statuses = [try_it(admin_client, link, tool).status_code for _ in range(11)]

    assert statuses == [200] * 10 + [429]
    assert len(wire.requests) == 10


def test_the_api_docs_describe_the_try_with_its_result():
    from drf_spectacular.generators import SchemaGenerator

    schema = SchemaGenerator().get_schema(request=None, public=True)

    path = schema["paths"]["/api/v1/channels/accounts/{account_id}/tools/{tool_id}/try/"]
    operation = path["post"]
    assert operation["operationId"] == "v1_channels_accounts_tools_try"
    result = schema["components"]["schemas"]["TryToolResult"]
    assert set(result["properties"]) == {"ok", "http_status", "body", "truncated", "error"}
    assert "values" in schema["components"]["schemas"]["TryToolRequest"]["properties"]


def test_trying_tools_does_not_use_up_the_limit_of_other_actions(tenant, admin_client, link):
    tool = add_tool(link)

    with network(*[answer(200, b"{}")] * 10, names=NAMES):
        for _ in range(10):
            try_it(admin_client, link, tool)
    invited = admin_client.post(
        "/api/v1/tenants/invitations/",
        {"email": "new@acme.test", "role": Membership.Role.AGENT},
        format="json",
    )

    assert invited.status_code == 201


def test_the_key_is_hidden_also_when_the_endpoint_sends_it_back_encoded(admin_client, link):
    import base64
    import json
    from urllib.parse import quote

    secret = "ab/cd+ef==sk"
    tool = add_tool(link, auth_secret=secret)
    forms = [
        json.dumps(secret)[1:-1].replace("/", "\\/"),  # JSON with the slash escaped
        quote(secret, safe=""),  # in an address
        base64.b64encode(secret.encode()).decode(),  # in base64
        base64.b64encode(f"Bearer {secret}".encode()).decode(),  # the whole header in base64
    ]
    # Each form as it would come in the text of the answer (not escaped once more)
    echo = ("seen: " + " | ".join(forms)).encode()

    with network(answer(200, echo), names=NAMES):
        response = try_it(admin_client, link, tool)

    body = response.data["data"]["body"]
    for form in forms:
        assert form not in body
    assert body.count("[hidden]") == len(forms)
