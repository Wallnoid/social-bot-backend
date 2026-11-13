## Story
As the Social Bot team, who pays for the AI of every business, I want a daily cap of bot replies per business, which I can raise or lower for each one, so that a spike or an abuse in one business cannot make the bill unlimited.

ClickUp: 1dfc7p9x0yn

## Acceptance criteria
- [ ] Given a business whose bots already sent the cap of replies of the day (from 00:00 to 23:59 in the business time zone, adding all its accounts), when a client writes to any of its accounts, then the message is saved, the bot does not answer and the AI is not called; a person can still answer.
- [ ] Given a new day starts, when a client writes, then the bot answers again, with nobody doing anything.
- [ ] Given a business that reached its cap, when its team looks at the active business, then it sees that the cap was reached and until when, and it hears about it in real time when it happens.

## Plan
- The business has an optional cap of its own. If it has none, it uses the server setting `BOT_MAX_REPLIES_PER_DAY` (500). Only the Social Bot team changes it, from the Django admin.
- The replies of the bot of today (outgoing messages with no human author) are counted across all the accounts of the business, with what is already saved: no new table and no AI. It is an approximation: a reply with several tool calls counts once.
- The check runs before the AI is called, next to the other protections of the bot.
- The active business shows `bot_daily_limit_until` (the next midnight, or `null`) in `GET /tenants/current/`. An event tells the team once when the cap is crossed; when midnight passes nothing is sent, as with the block and the hourly limit.
- Tests: right at the cap, the next day, several accounts of the same business, replies of people that do not count, another business not affected, the own cap against the general one, and the event.

## Out of scope
- Recording how much AI each business used and its price (story B below).
- Letting the business admin see or change the cap.
- Telling someone by email or notification (that module does not exist yet).
- Telling the client: the bot stays silent, as with the hourly limit.
- Counting AI calls or tokens instead of replies.

## Decisions (agreed)
- The value is 500 replies per business per day, a safety net and not normal use; it is changed with an environment variable, and a business can have its own.
- The signal lives in `GET /tenants/current/` (so a reload still knows) plus an event; nothing else is notified yet.
- Only the Social Bot team changes the cap of a business, from the Django admin: it protects the platform's spending, so the business must not raise it by itself.
- All the accounts of the business are added together.

## Related story (to add to the tracker)
B. As the Social Bot team, I want to know how much AI each business used each day (calls and tokens, by model), so that I can bill them for it.
- The AI provider does not report usage through `wanps-core`, but the original Gemini response carries it (`raw.usage_metadata`), so it can be read from this repo by wrapping the provider in the handler, without touching `wanps-core`.
- One row per business, day and model with calls and tokens; the price in money is calculated later, so a price that changes is not fixed in the data. Read by the team from the Django admin.
- Needed before a cap by tokens could exist.

## Suggestions (your call)
- The warning of the cap is about the whole business, not about one client, so the frontend shows it once at the top and not in every row of the inbox.
