## Story
As the Social Bot team, who pay for the AI of every business, I want a client who insists on messages unrelated to the business to get warnings and then a temporary block that costs no AI, so that nobody abuses the service.

## Acceptance criteria
- [ ] Given a client who sends a message unrelated to the business, when the bot detects it, then a fault is counted; from the second fault the bot tells the client how many chances are left before the block.
- [ ] Given a client who reaches the maximum of faults, when it is reached, then the bot tells the client in that same message and the client is blocked for a time; during the block their messages are kept but nothing is sent to the AI and the bot does not answer.
- [ ] Given a blocked client, when the time of the block passes, then the bot attends them again; the faults expire after a time without new ones.
- [ ] Given a chat with a blocked client, when the team sees it, then the inbox shows until when, and an admin or a supervisor can lift the block (in case it was a mistake).

## Plan
- An internal tool, `flag_off_topic`, that the AI calls when a message has nothing to do with the business. The server counts the fault and answers with how many chances are left (or with the length of the block), so the AI writes the warning in the language of the client.
- A table with the faults, the start of the window and the end of the block of each client in each account, updated atomically.
- Before building the context or calling the AI, the handler checks the block: a blocked client costs no AI at all. Only the bot is blocked: a person can always answer.
- The numbers come from settings: 5 faults, warning from the 2nd, faults expire after 24 hours without new ones, block of 60 minutes, and 24 hours if the same client is blocked again within a day.
- The inbox shows `bot_blocked_until`, and a supervisor or an admin can lift the block with its own endpoint.

## Out of scope
- A limit of messages per client per hour and a daily cap of AI answers per account (their own stories).
- A classifier before the AI, and a fixed text for the warnings.
- Blocking a person, not only the bot, or blocking a number across businesses.

## Decisions made
- The AI detects the off-topic messages with a tool, so no extra call is made; the first faults are still answered by the AI, which is why the block limits the cost but does not remove it.
- The warning and the message of the block are written by the AI, with the exact number of chances or the time of the block that the tool gives it.
- The rule of when to call the tool ("only if clearly unrelated; greetings and thanks do not count; when in doubt, answer normally") is one of the rules of the platform.
- A client can try another number: this is not solved here.
