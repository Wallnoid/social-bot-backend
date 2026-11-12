## Story
As a business admin, I want to turn the bot of a channel account on or off and tell it how to behave, so that my business answers its clients automatically with my instructions.

## Acceptance criteria
- [ ] Given an account of my business, when I (an admin) write its instructions and turn the bot on, then the bot answers the new messages of clients on that account following those instructions, written in the format the channel understands; when I turn it off, it stops answering while the messages keep arriving. An agent or a supervisor gets 403, and an account of another business is not found.
- [ ] Given an account of my business, when any member reads it, then they see whether the bot is on and its instructions, and never the token or any AI key.
- [ ] Given the bot cannot answer yet (the instructions are empty, or no AI is available), when I try to turn it on, then I get a clear error and it stays off.

## Plan
- Connect the AI of the platform (provider, model and key already in `.env`, with a timeout and a low effort, as in `whatsapp-bot`) so accounts without an AI of their own use it; the key is never returned by the API.
- A handler of this project, based on `BaseAIHandler`, is the default one for every account: its prompt is the instructions of the account plus the formatting rule of the channel (WhatsApp `*bold*`, plain text on Messenger and Instagram). The rule goes in the base prompt, so it applies at every AI level.
- The edit of an account also takes the on/off switch and the instructions; reading it shows both.
- Turning it on is refused if there are no instructions, or if neither the platform nor the account has an AI.
- Messages are processed by the Celery worker (`WANPS_ASYNC`), so Meta gets its answer at once while the AI thinks.

## Out of scope
- AI levels 2 and 3, tools and the panel to create them (stories for the tools panel, its safe execution and its test).
- Choosing the provider, model, level or an own key per business: stays with Social Bot staff in the Django admin.
- Pausing the bot in a single chat (already exists), usage limits or billing, and trying the bot from the UI.

## Decisions made
- The AI is the one of the platform (Social Bot pays); the key lives in `.env`.
- The business admin only turns the bot on or off and writes its instructions. The AI level stays basic (prompt only, no tools) until the tools stories.
- The instructions are visible to any member: they are not a secret, and it avoids a different answer per role.
- A bot without instructions cannot be turned on: it would answer clients with no guidance at all.
- The business context is plain text (the instructions); structured knowledge (questions and answers, documents) is not supported by `wanps-core` and is left for later.
- `WANPS_ASYNC` is read from `.env` in the settings and turned on in `.env`; accounts leave their own switch empty, so they follow the global one.
- No change in `wanps-core`: the handler of this project covers what is needed.
