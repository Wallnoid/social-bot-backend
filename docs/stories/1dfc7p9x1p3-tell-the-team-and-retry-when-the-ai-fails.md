## Story
As a business member, I want to see when the bot could not answer a client because the AI failed, and the bot to try again, so that no client is left without an answer without me knowing.

ClickUp: 1dfc7p9x1p3

## Acceptance criteria
- [ ] Given a message of a client that the bot could not answer because the AI failed, when the team looks at the list or the chat, then it sees that the bot could not answer that client and since when, hears about it in real time, and can answer by hand.
- [ ] Given that failure, when a few minutes pass and that message is still the last thing in the chat (no new message of the client and no reply of a person), then the bot tries again, and stops trying one hour after the message.
- [ ] Given a chat with the failure warning, when the bot manages to answer or a person replies, then the warning goes away and the team hears about it in real time.

## Plan
- The handler tells the errors of the AI provider apart from the other errors. Only for the first ones it saves the failure of the chat (message, date and attempts) and schedules the retry.
- The retries go through Celery, with growing gaps and a limit of one hour from the message. Before each attempt it checks that the message is still the last thing in the chat and that there is no pause, block or limit.
- The list and the chat show `bot_failed_at` (a date or `null`), and an event tells the team when it appears and when it goes away. Here the warning always goes away by an action of the server, so there is always an event.
- A reply of the bot or of a person in that chat clears the failure.
- Tests: an AI failure against another failure, a retry that works, a new message that cancels the retry, the one-hour limit, a reply of a person that clears the warning, isolation between businesses, and the events.

## Out of scope
- Telling the client with an automatic text.
- Notifying by email or phone (the notifications module does not exist yet).
- Switching to another AI provider or model when one fails.
- Retrying failures that are not of the AI, like the send to Meta.

## Decisions (agreed)
- 4 retries, at 1, 5, 15 and 30 minutes from the failure; adjustable from the settings.
- No automatic text to the client: without the AI it could only be a fixed text in one language.
- The warning appears from the first failure, even while retries are left, so the team can answer without waiting; if a retry works the warning goes away by itself.

## Notes
- If Gemini stops because of the daily quota of its plan, retrying for an hour does not fix it; the warning is what helps then.
