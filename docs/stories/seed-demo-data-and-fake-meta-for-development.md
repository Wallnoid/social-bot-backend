## Story
As a frontend developer, I want to seed realistic test data and be able to send messages without calling Meta, so that I can try every screen (inboxes, 24-hour windows, bot, roles, several businesses, load more) without real accounts.

## Acceptance criteria
- [ ] Given the development environment with the test password defined, when I run the seeding, then the test businesses, accounts, conversations, messages and users are created, with dates relative to now, and when it ends I see a summary of what was created (without the password); if I run it again nothing is duplicated, and with `--reset` only what was seeded is deleted and created again.
- [ ] Given I am not in development (DEBUG off) or the test password is missing, when I run the seeding, then it refuses to run and touches nothing.
- [ ] Given the development environment, when I send a message from the inbox with a seeded account, then it is saved and shown as sent without calling Meta; if the text contains `#fail`, the API answers the delivery error (502) and nothing is saved; in production that mode does not exist.

## Plan
- A development tools app that is only installed in the local settings; it holds the seeding command and the fake Meta. Production does not include it.
- The seeding creates two new demo businesses and marks everything with the `demo-` prefix (names, account ids and contact ids), so `--reset` deletes only its own data. If the seeded data already exists, it says so and does not duplicate it.
- The data:
  - 2 WhatsApp accounts, 1 Messenger, 1 Instagram and 1 inactive, with fake tokens.
  - About 8 conversations per channel (window open and closed, more than 7 days on Messenger and Instagram, bot active, paused without a date and with a date, the same client in two accounts).
  - A chat of more than 120 messages with long texts, line breaks, emojis and a long link.
  - Every value of direction, type (text, image, document, audio), status (including a failed one) and sender (client, bot, person), with bot messages after a human reply.
  - More than 150 conversations on one channel, to try "load more".
  - One user per role and one user who belongs to both businesses.
- The fake Meta intercepts the sending calls to Meta and answers like Meta (with a message id), except with `#fail`, where it answers a rejection. The views do not change.
- The password of the test users comes from `SEED_DEMO_PASSWORD`: it is not written in the repository nor printed.

## Out of scope
- Simulating incoming messages (a separate story).
- Real image, document or audio files: the messages have the right type, with the usual placeholder.
- Faking the list of templates (it comes with story D).
- Changes in the API or in the OpenAPI schema.

## Decisions made
- The seeding creates new demo businesses instead of using the test user's business, so no real data is ever touched. An option `--member <email>` adds that user as admin of both demo businesses, so they can log in with their usual account.
- `#fail` in the text forces the 502. The 409 needs no switch: it comes from sending text to a seeded conversation whose window is closed.
- Pausing and resuming the bot never calls Meta, so it already works without the fake.
- The data must not change any contract: the OpenAPI schema stays the same.
