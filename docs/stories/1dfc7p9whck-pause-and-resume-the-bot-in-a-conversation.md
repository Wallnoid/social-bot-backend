## Story
As a business member, I want to pause and resume the bot in a conversation, so that I can handle a chat myself when needed and give it back to the bot afterwards.

## Acceptance criteria
- [ ] Given a chat of my business, when I pause the bot (for a while or until I resume it), then the bot stops replying in that chat and in no other, the client's messages keep being stored, and the chat shows that the bot is paused, who paused it and until when.
- [ ] Given a chat with the bot paused (by me, by someone else or because someone replied), when I resume it, then the bot replies again in that chat and the chat shows it is no longer paused; if the pause had a time, the bot also comes back by itself when it ends.
- [ ] Given the account belongs to another business or is disconnected, the chat does not exist or the time is not valid, when I try to pause or resume, then the API rejects it (404 or 400) and nothing changes.

## Plan
- One action per chat of each channel to pause or resume the bot, open to any member of the active business, with the account required as when reading and sending.
- The pause or resume is done by `wanps.inbox`, limited to the business's accounts as in the previous stories.
- When pausing, who did it (the member's name) is stored and, if given, for how many minutes; without a time, the pause lasts until someone resumes.
- The chat must exist for that account (with at least one message); an account of another business, a disconnected one or an invalid time are rejected without changing anything.
- The response returns the bot's state in the chat with the same fields the list and the messages already show.

## Out of scope
- Turning the bot on for an account and configuring it: instructions, handler, AI (story E).
- Pausing or resuming all the chats of an account at once.
- Notices when the bot is paused, and seeing it live (story C).
- Resuming automatically when the client writes, or after a person stops replying.

## Decisions made
- Every role can pause and resume: business rule 6 says a person can pause the bot in a conversation, and whoever replies already pauses it.
- The chat must exist: otherwise any member could create conversation records for made-up ids.
- The pause time has a maximum of 10,080 minutes (one week): without a limit a huge number breaks the date calculation. A longer pause is made without a time (until resumed).
- Until story E exists, no account has its bot on (every account starts with `is_active: false`), so pausing and resuming only has a visible effect once an account is turned on.
