## Story
As a business admin, I want to try a tool of the bot with sample values before turning it on, so that I see it works with real data and do not find the errors with my clients.

ClickUp: 1dfc7p9wz3q

## Acceptance criteria
- [ ] Given a tool of my business (on or off), when I try it with sample values, then I see whether it worked, the HTTP status and the beginning of what the endpoint answered, with the same security controls the bot uses.
- [ ] Given a try that fails (blocked address, no answer, too slow or too big, an error status, or values that are missing or of the wrong type), when I make it, then I see the reason with a clear code, and nothing else breaks.
- [ ] Given a tool with a key, when I try it, then the key never appears in the result, even if the endpoint sends it back.

## Plan
- A new action on each tool: the admin sends sample values and the very same call the bot makes runs (validation, key and the security controls).
- The answer says whether it worked, the HTTP status and the first characters of the answer, or an error code with its reason.
- Before returning the text, the key of the tool is hidden if it appears.
- Only admins of the business, only their own tools, with a limit of tries per minute.
- Tests: a successful try, each kind of failure, invalid values, the hidden key, a tool that is off, another business and another role refused, and the limit.

## Out of scope
- The screen of the frontend to try (this is only the API).
- Passing the answer through the AI to see what the bot would say.
- Methods other than GET (the tools only do GET).

## Decisions (agreed)
- The first 2000 characters of the answer are shown: enough to see the shape of a JSON without bringing whole pages.
- The try is kept in the record of calls, like the ones of the bot: it is a real call to a third party.
- 10 tries per minute per user, so nobody uses the try as an address scanner.
- A tool that is off can be tried: that is exactly the case of use, to try before turning it on.
- A risk the card does not mention: some endpoints send back what they receive (an echo service, or one that answers with the authorization header), so the key is hidden in the result.
