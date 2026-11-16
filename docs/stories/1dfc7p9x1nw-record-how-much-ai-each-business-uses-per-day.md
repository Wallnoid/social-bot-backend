## Story
As the Social Bot team, I want to know how much AI each business used each day (calls and tokens, by model), so that I can bill them for it.

ClickUp: 1dfc7p9x1nw

## Acceptance criteria
- [ ] Given a bot that answers a client, when the AI answers, then the day of the business (in its time zone), by model, adds how many calls there were and how many input, output and thinking tokens were used; a turn with tools adds each call.
- [ ] Given a day or a range of dates and a business, when the Social Bot team looks at it in the Django admin, then it sees the usage by day and model, and the total of the filtered range, telling apart what was paid with the key of the platform from what was paid with the own key of the business.
- [ ] Given that the provider does not report the usage of a call, or that recording it fails, when it happens, then the bot answers anyway; the call counts with zero tokens or, if the recording failed, it is only in the log.

## Plan
- A table with one row per business, day, model and who pays, adding calls and the three kinds of tokens with an atomic increment. No prices.
- The wrapper of the provider reads the usage of each answer and adds it to that row, in one query.
- The Django admin lists those rows with filters by business, date and who pays, and shows the total of what is filtered at the top. Read only.
- Tests: an answer adds, a turn with tools adds each call, day, model and business kept apart, the own key kept apart from the platform one, an answer with no usage, an error while recording that does not stop the bot, and the total in the admin.

## Out of scope
- Prices, amounts of money and invoices.
- Letting the business admin see its usage in the frontend.
- A cap by tokens instead of the cap by replies that already exists.
- Counting the calls that failed.
- Detail per call or per client.

## Decisions (agreed)
- A call made with the own AI key of an account is recorded apart (paid by the business), so it is visible but not billed.
- The day is the one of the business time zone (`BUSINESS_TIME_ZONE`), as in the daily cap, so "the day" means the same in both.
- Only the daily total is kept: it is enough to bill, and the detail per call grows fast.

## Notes
- Gemini gives the usage in the original response (`usage_metadata`): input, output and thinking tokens. Google bills the thinking tokens as output, so they are kept too.
- A call that fails brings no usage and is usually not billed, so only the calls that answered are counted.

## Suggestions (your call)
- The wrapper of the provider would do two things: tell failures apart and measure usage. It is the same point every call goes through, so it makes sense there; if it grows more it could be split in two.
