## Story
As a business member who answers a client by hand, I want the bot to take the chat back on its own after an hour without a reply from a person, so that a client is not left unanswered just because someone forgot to resume the bot.

## Acceptance criteria
- [ ] Given I reply to a client from the inbox, when the reply is sent, then the bot stays silent in that chat for one hour from that reply (each new reply of a person starts the hour again), and the chat shows until when (`bot_paused_until`).
- [ ] Given an hour has passed since the last reply of a person, when the client writes again, then the bot answers.
- [ ] Given I pause the bot myself from the inbox (for some minutes, or until resumed), when I do, then it behaves as it does today: only what I chose, nothing extra.

## Plan
- On sending as a person, pause the bot with an end time one hour ahead, using the pause that already supports it.
- The pause ends on its own: no job, no new table.
- The time comes from a setting, one hour by default.

## Out of scope
- Resuming from the moment the client writes without an answer (the hour counted from the client's message).
- A different time per business or per account.
- Telling the client or the team that the bot came back.

## Decisions made
- The hour is counted from the last reply of a person (option A): while a person keeps talking, the bot never steps in; when they leave, the bot comes back an hour later.
- One time for every business, from the setting `BOT_RESUME_AFTER_MINUTES` (60 by default). A time per business can come later.
- A pause the member makes by hand keeps working as before, for the minutes they choose or until resumed.
- The frontend needs no change: it already receives `bot_paused_until`, which used to be empty after a reply and now holds the hour.
