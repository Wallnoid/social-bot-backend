"""
The bot of every account: the instructions its business wrote, how its channel shows text, and the
tools the business gave it.
"""

import logging

from wanps.ai import BaseAIHandler
from wanps.ai.handlers import AI_LEVEL_TOOLS
from wanps.ai.tools import Tool

from .abuse import check_daily_limit, check_flooding, is_blocked
from .bot_context import context_block, internal_tools
from .failures import AIUnavailableError, GuardedProvider, record_failure
from .models import ChannelTool
from .platform_rules import rules_block
from .safe_http import safe_get
from .usage import tenant_of

logger = logging.getLogger(__name__)

# Each channel renders text differently, so the rule depends on where the message came from.
# A channel that is not listed gets plain text, which is safe everywhere.
FORMAT_RULES = {
    "whatsapp": (
        "- Use WhatsApp formatting: *bold* with a single asterisk and _italic_ with underscores. "
        "Do not use Markdown (no **, no # and no [text](url) links)."
    ),
}
PLAIN_TEXT_RULE = (
    "- Write plain text: no bold or italics, no asterisks or underscores to format, and no "
    "Markdown (no **, no # and no [text](url) links). To list things, use one line for each."
)


# What the AI may give for each declared type (a list or a dict is never a value of a query)
TYPE_CHECKS = {
    "string": lambda value: isinstance(value, (str, int, float)) and not isinstance(value, bool),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
}


def query_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def tool_request(tool, arguments):
    """
    The headers and the query of the call of a tool, from the values given: the ones the tool
    declares, checked. Raises ValueError when a required value is missing or has the wrong type.
    The bot and the try of an admin both build their call here.
    """
    declared = {parameter["name"]: parameter["type"] for parameter in tool.parameters}
    required = [parameter["name"] for parameter in tool.parameters if parameter["required"]]
    missing = [name for name in required if arguments.get(name) in (None, "")]
    if missing:
        raise ValueError("Missing required value: " + ", ".join(missing))
    values = {
        name: value for name, value in arguments.items() if name in declared and value is not None
    }
    wrong = [name for name, value in values.items() if not TYPE_CHECKS[declared[name]](value)]
    if wrong:
        raise ValueError("Wrong type of value: " + ", ".join(wrong))
    headers = {}
    if tool.auth_type == ChannelTool.AuthType.BEARER:
        headers["Authorization"] = f"Bearer {tool.auth_secret}"
    elif tool.auth_type == ChannelTool.AuthType.HEADER:
        headers[tool.auth_header] = tool.auth_secret
    return headers, {name: query_value(value) for name, value in values.items()}


def build_tool(tool):
    """
    The AI-facing tool of a ChannelTool: a GET to its address with the values the AI gives in the
    query and the key of the tool. Only the values the tool declares are sent.
    """
    required = [parameter["name"] for parameter in tool.parameters if parameter["required"]]
    schema = {
        "type": "object",
        "properties": {
            parameter["name"]: {"type": parameter["type"], "description": parameter["description"]}
            for parameter in tool.parameters
        },
    }
    if required:
        schema["required"] = required

    # `account` is filled in by wanps-core with the account of the message, never by the AI
    def call(*, account, **arguments):
        headers, params = tool_request(tool, arguments)
        return safe_get(tool.url, account=account, tool=tool.name, headers=headers, params=params)

    return Tool(call, name=tool.name, description=tool.description, parameters_schema=schema)


def business_of(account):
    """The business of the account, even if it was deleted (one lookup for the whole message)."""
    from apps.tenants.models import Tenant

    return Tenant.all_objects.filter(channel_accounts__account=account).first()


def is_off(tenant) -> bool:
    """The Social Bot team suspended the business, or it was deleted."""
    return tenant is not None and (tenant.suspended_at is not None or tenant.is_deleted)


class ChannelAIHandler(BaseAIHandler):
    """Answers with the instructions of the account, written for the channel of the client."""

    def active_tools(self, msg):
        """
        The tools of the account of the message, and of no other account. Looked up once: wanps-core
        asks for the level and for the tools in the same turn.
        """
        account = self.get_account(msg)
        if account is None:
            return []
        cache = self.__dict__.setdefault("_active_tools", {})
        if account.pk not in cache:
            cache[account.pk] = list(ChannelTool.objects.filter(account=account, is_active=True))
        return cache[account.pk]

    def handle(self, msg) -> None:
        account = self.get_account(msg)
        # The API does not let the bot be on without instructions, but the Django admin does:
        # a bot with no guidance would answer the clients of a business with anything
        if account is not None and not account.system_prompt.strip():
            logger.warning(
                "Account %s has the bot on without instructions: not answering.", account.pk
            )
            return
        # A suspended or deleted business has no bot: its messages are kept, nothing more
        tenant = business_of(account) if account is not None else None
        if is_off(tenant):
            logger.info("The business of message %s is off: not answering.", msg.external_id)
            return
        # A blocked client costs no AI at all: nothing is built and nothing is sent
        if account is not None and is_blocked(account, msg.contact_id):
            logger.info("The client of message %s is blocked: not answering.", msg.external_id)
            return
        # Too many messages in an hour: the bot stays silent and the AI is not called. A person can answer
        if account is not None and check_flooding(account, msg.contact_id):
            logger.info("The client of message %s writes too much: not answering.", msg.external_id)
            return
        # The business used the replies of its day: nothing is sent to the AI until tomorrow
        if account is not None and tenant is not None and check_daily_limit(account, tenant):
            logger.info(
                "The business of message %s used its daily replies: not answering.", msg.external_id
            )
            return
        # The calls to the AI are counted per turn: a retry starts again from zero
        turns = self.__dict__.setdefault("_ai_calls", {})
        turns[msg.pk] = 0
        try:
            super().handle(msg)
        finally:
            turns.pop(msg.pk, None)
            self.__dict__.get("_ai_tenants", {}).pop(msg.pk, None)

    def get_message_provider(self, msg):
        # Only an error of the AI provider is a failure the bot may try again: anything else (the
        # prompt, the tools) is a bug
        turns = self.__dict__.setdefault("_ai_calls", {})
        account = self.get_account(msg)
        # The business of the account is looked up once for the turn, not for each call
        tenants = self.__dict__.setdefault("_ai_tenants", {})
        if msg.pk not in tenants:
            tenants[msg.pk] = tenant_of(account) if account is not None else None
        return GuardedProvider(
            super().get_message_provider(msg), turns, msg.pk, account, tenants[msg.pk]
        )

    def on_error(self, msg, error) -> None:
        super().on_error(msg, error)
        if isinstance(error, AIUnavailableError):
            record_failure(msg, retry=error.retry)

    def get_base_system_prompt(self, msg) -> str:
        # The base prompt is the one every AI level uses, so the rule always applies
        instructions = super().get_base_system_prompt(msg).rstrip()
        rule = FORMAT_RULES.get(msg.channel, PLAIN_TEXT_RULE)
        context = context_block(msg)
        parts = [
            instructions,
            "",
            context,
            "",
            rules_block(),
            "",
            "Format of the answers:",
            rule,
            "",
        ]
        return "\n".join(parts)

    def get_ai_level(self, msg) -> int:
        # The bot of an account always has the internal tools, so it always uses the tools level
        level = super().get_ai_level(msg)
        return max(level, AI_LEVEL_TOOLS) if self.get_account(msg) is not None else level

    def get_tools(self, context, msg):
        return [*internal_tools(), *(build_tool(tool) for tool in self.active_tools(msg))]
