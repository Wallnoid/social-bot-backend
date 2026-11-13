"""
The bot using the tools of its account, end to end: the AI is offered only the active tools of the
account that received the message, and when it asks for one the endpoint is called with the values
it gave and the key of the tool. The AI is a scripted fake and the endpoint is replaced.
"""

from types import SimpleNamespace
from unittest import mock

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from wanps.ai.types import AIResponse, ToolCall
from wanps.messaging.models import Account

from apps.channels.handler import ChannelAIHandler
from apps.channels.models import ChannelTool
from apps.channels.safe_http import ToolCallError
from apps.channels.tests.test_bot import turn_on
from apps.channels.tests.test_bot_replies import REPLY, client_writes
from apps.channels.tests.test_manage_accounts import add_account
from apps.channels.tests.test_tools import SECRET, TOOL, tools_url
from apps.conversations.tests.test_send import meta_replies, recipient_and_text
from apps.tenants.models import Tenant

CLIENT = "593990000001"
SAFE_GET = "apps.channels.handler.safe_get"
# The tools every bot has, whatever the tools its business gave it
INTERNAL_TOOLS = ["get_client_info", "get_previous_messages", "flag_off_topic"]

pytestmark = pytest.mark.usefixtures("inline_processing_and_platform_ai", "no_real_meta_profiles")


class ScriptedAI:
    """Stands for the AI: says what the script says, and remembers what it was offered and told."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.offered = []
        self.tool_results = []
        self.prompts = []

    def generate(self, context, system_prompt="", tools=None):
        self.prompts.append(system_prompt)
        schemas = tools.to_openai() if tools is not None else []
        self.offered.append([schema["function"] for schema in schemas])
        self.tool_results.append([m.content for m in context.messages if m.role == "tool"])
        return self.replies.pop(0) if self.replies else REPLY

    def offered_names(self, call=0):
        return [schema["name"] for schema in self.offered[call]]


def asks_for(name="opening_hours", **arguments):
    return AIResponse(tool_calls=[ToolCall(id="call-1", name=name, arguments=arguments)])


@pytest.fixture
def link(admin_client, tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    assert turn_on(admin_client, link).status_code == 200
    return link


def add_tool(admin_client, link, **overrides):
    response = admin_client.post(tools_url(link), {**TOOL, **overrides}, format="json")
    assert response.status_code == 201
    return response


def client_writes_to(client, meta_app, ai, number="111", endpoint=None):
    """The client writes to the number; the AI and the endpoint of the tools are the fakes."""
    endpoint = endpoint or mock.Mock(return_value="Open from 9:00 to 17:00.")
    with (
        mock.patch("wanps.ai.handlers.provider_from_settings", return_value=ai),
        mock.patch(SAFE_GET, endpoint),
        meta_replies("whatsapp") as post,
    ):
        response = client_writes(client, meta_app, "whatsapp", number)
    assert response.status_code == 200
    return endpoint, post


def test_the_ai_is_offered_the_active_tools_of_the_account_with_their_parameters(
    admin_client, client, meta_app, link
):
    add_tool(admin_client, link)
    old = add_tool(admin_client, link, name="old_tool").data["data"]["id"]
    admin_client.patch(f"{tools_url(link)}{old}/", {"is_active": False}, format="json")
    ai = ScriptedAI()

    client_writes_to(client, meta_app, ai)

    assert ai.offered_names() == [*INTERNAL_TOOLS, "opening_hours"]
    offered = next(tool for tool in ai.offered[0] if tool["name"] == "opening_hours")
    assert offered["description"] == TOOL["description"]
    assert offered["parameters"] == {
        "type": "object",
        "properties": {"day": {"type": "string", "description": "Day of the week"}},
        "required": ["day"],
    }
    # The level of the account stays as it was: it is derived while there are tools
    assert Account.objects.get(pk=link.account_id).ai_level == 1


@pytest.mark.parametrize(
    ("number", "expected"),
    [("111", [*INTERNAL_TOOLS, "opening_hours"]), ("222", [*INTERNAL_TOOLS, "rival_tool"])],
)
def test_the_ai_is_offered_only_the_tools_of_the_account_that_got_the_message(
    admin_client, client, meta_app, link, number, expected
):
    add_tool(admin_client, link)
    rival = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "222")
    Account.objects.filter(pk=rival.account_id).update(is_active=True, system_prompt="Rival bot")
    ChannelTool.objects.create(
        account=rival.account, name="rival_tool", description="d", url="https://rival.example/x"
    )
    ai = ScriptedAI()

    client_writes_to(client, meta_app, ai, number=number)

    assert ai.offered_names() == expected


def test_an_account_without_tools_of_its_own_is_offered_only_the_internal_ones(
    client, meta_app, link
):
    ai = ScriptedAI()

    client_writes_to(client, meta_app, ai)

    assert ai.offered_names() == INTERNAL_TOOLS


def test_when_the_ai_asks_for_a_tool_the_endpoint_gets_the_values_and_the_key(
    admin_client, client, meta_app, link
):
    add_tool(admin_client, link)
    ai = ScriptedAI(asks_for(day="monday"))

    endpoint, _ = client_writes_to(client, meta_app, ai)

    endpoint.assert_called_once()
    assert endpoint.call_args.args == (TOOL["url"],)
    kwargs = endpoint.call_args.kwargs
    assert kwargs["account"] == link.account
    assert kwargs["tool"] == "opening_hours"
    assert kwargs["params"] == {"day": "monday"}
    assert kwargs["headers"] == {"Authorization": f"Bearer {SECRET}"}


def test_a_key_in_a_header_goes_in_the_header_named_by_the_admin(
    admin_client, client, meta_app, link
):
    add_tool(admin_client, link, auth_type="header", auth_header="X-Api-Key")
    ai = ScriptedAI(asks_for(day="monday"))

    endpoint, _ = client_writes_to(client, meta_app, ai)

    assert endpoint.call_args.kwargs["headers"] == {"X-Api-Key": SECRET}


def test_a_tool_without_authentication_sends_no_key(admin_client, client, meta_app, link):
    add_tool(admin_client, link, auth_type="none", auth_secret="")
    ai = ScriptedAI(asks_for(day="monday"))

    endpoint, _ = client_writes_to(client, meta_app, ai)

    assert not endpoint.call_args.kwargs["headers"]


def test_the_answer_of_the_endpoint_goes_back_to_the_ai_and_its_reply_reaches_the_client(
    admin_client, client, meta_app, link
):
    add_tool(admin_client, link)
    ai = ScriptedAI(asks_for(day="monday"), "We open from nine to five.")

    _, post = client_writes_to(client, meta_app, ai)

    assert ai.tool_results[1] == ["Open from 9:00 to 17:00."]
    assert recipient_and_text("whatsapp", post.call_args.kwargs["json"]) == (
        CLIENT,
        "We open from nine to five.",
    )


def test_a_value_the_tool_did_not_declare_is_never_sent(admin_client, client, meta_app, link):
    add_tool(admin_client, link)
    ai = ScriptedAI(asks_for(day="monday", evil="https://internal.example"))

    endpoint, _ = client_writes_to(client, meta_app, ai)

    assert endpoint.call_args.kwargs["params"] == {"day": "monday"}


def test_a_missing_required_value_is_told_to_the_ai_and_the_endpoint_is_not_called(
    admin_client, client, meta_app, link
):
    add_tool(admin_client, link)
    ai = ScriptedAI(asks_for(), "Which day?")

    endpoint, post = client_writes_to(client, meta_app, ai)

    endpoint.assert_not_called()
    assert "day" in ai.tool_results[1][0]
    assert recipient_and_text("whatsapp", post.call_args.kwargs["json"])[1] == "Which day?"


def test_a_failing_endpoint_gives_the_ai_a_short_safe_error_and_the_bot_still_answers(
    admin_client, client, meta_app, link
):
    add_tool(admin_client, link)
    ai = ScriptedAI(asks_for(day="monday"), "I could not check it now.")
    endpoint = mock.Mock(side_effect=ToolCallError("http_error", 500))

    _, post = client_writes_to(client, meta_app, ai, endpoint=endpoint)

    (told,) = ai.tool_results[1]
    assert "status 500" in told and SECRET not in told
    assert recipient_and_text("whatsapp", post.call_args.kwargs["json"])[1] == (
        "I could not check it now."
    )


NUMBER = [{"name": "party_size", "type": "number", "description": "People", "required": True}]


@pytest.mark.parametrize("wrong", [[1, 2], {"a": 1}, True, "four"])
def test_a_value_of_the_wrong_type_is_told_to_the_ai_and_the_endpoint_is_not_called(
    admin_client, client, meta_app, link, wrong
):
    add_tool(admin_client, link, name="book", parameters=NUMBER)
    ai = ScriptedAI(asks_for("book", party_size=wrong), "Could you tell me the number again?")

    endpoint, _ = client_writes_to(client, meta_app, ai)

    endpoint.assert_not_called()
    assert "party_size" in ai.tool_results[1][0]


@pytest.mark.parametrize(
    ("declared", "given", "sent"),
    [
        ("number", 4, "4"),
        ("number", 2.5, "2.5"),
        ("string", "Quito", "Quito"),
        ("string", 170101, "170101"),
        ("boolean", True, "true"),
        ("boolean", False, "false"),
    ],
)
def test_values_of_the_declared_type_go_in_the_query_as_text(
    admin_client, client, meta_app, link, declared, given, sent
):
    parameters = [{"name": "value", "type": declared, "description": "d", "required": True}]
    add_tool(admin_client, link, name="check", parameters=parameters)
    ai = ScriptedAI(asks_for("check", value=given))

    endpoint, _ = client_writes_to(client, meta_app, ai)

    assert endpoint.call_args.kwargs["params"] == {"value": sent}


def test_the_tools_of_a_message_are_looked_up_once(admin_client, link):
    add_tool(admin_client, link)
    handler = ChannelAIHandler()
    msg = SimpleNamespace(account=link.account, channel="whatsapp")

    with CaptureQueriesContext(connection) as queries:
        handler.get_ai_level(msg)
        handler.get_tools(None, msg)
        handler.get_ai_level(msg)

    on_tools = [q for q in queries if "channels_channeltool" in q["sql"]]
    assert len(on_tools) == 1
