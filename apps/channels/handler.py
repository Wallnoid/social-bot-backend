"""
The bot of every account: the instructions its business wrote, plus how its channel shows text.
"""

import logging

from wanps.ai import BaseAIHandler

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


class ChannelAIHandler(BaseAIHandler):
    """Answers with the instructions of the account, written for the channel of the client."""

    def handle(self, msg) -> None:
        account = self.get_account(msg)
        # The API does not let the bot be on without instructions, but the Django admin does:
        # a bot with no guidance would answer the clients of a business with anything
        if account is not None and not account.system_prompt.strip():
            logger.warning(
                "Account %s has the bot on without instructions: not answering.", account.pk
            )
            return
        super().handle(msg)

    def get_base_system_prompt(self, msg) -> str:
        # The base prompt is the one every AI level uses, so the rule always applies
        instructions = super().get_base_system_prompt(msg).rstrip()
        rule = FORMAT_RULES.get(msg.channel, PLAIN_TEXT_RULE)
        return "\n".join([instructions, "", "Format of the answers:", rule, ""])
