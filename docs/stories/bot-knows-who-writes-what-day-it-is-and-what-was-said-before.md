## Story
As a business, I want the bot to know who writes to it, what day and time it is and what was said before, so that it answers with context and not as if every message were the first one.

## Acceptance criteria
- [ ] Given a client who writes to an account with the bot on, when the bot answers, then it already knows the name and the channel of the client (or that it does not have the name), the name, industry and description of the business, and the current date and time in the time zone of the business.
- [ ] Given a client who had written before, when the bot needs to know more about them, then it can look up their file (name, channel, phone only on WhatsApp, date of the first contact, how many messages they have exchanged and the last time they wrote before today).
- [ ] Given a long conversation or one from other days, when the bot needs what was said before what it already remembers, then it can look up the earlier messages (up to 30) with their date and who wrote each one.

## Plan
- A block of context in the prompt with the data of the client and of the business and the time in the zone `BUSINESS_TIME_ZONE` (`America/Guayaquil` by default).
- Two internal read-only tools, always on: the file of the client and the earlier messages. The account and the client come from the message, never from what the AI asks for.
- The phone is only given on WhatsApp.
- Tests by channel, for isolation between clients and businesses, and end to end with a fake AI.

## Out of scope
- Handing the chat over to a person (own story), the rules of the platform (own story), a time zone per business, and appointments or CRM (those modules do not exist).

## Decisions made
- What every conversation needs goes in the prompt, not in a tool: it costs a few tokens and saves a round trip to the AI. The tools are for what is asked only sometimes.
- The internal tools are always on, with no screen to configure them. Because of them every account uses the tools level, and each tool call is one more call to the AI.
- The time zone is a server setting for now, not a field of the business.
- The phone only goes to the AI on WhatsApp, where it already identifies the client. Everything the AI sees travels to the AI provider.
- "Earlier messages" are the last ones of the chat before the one being answered, newest 30 in order of time; the bot may already remember some of them, which does no harm.
