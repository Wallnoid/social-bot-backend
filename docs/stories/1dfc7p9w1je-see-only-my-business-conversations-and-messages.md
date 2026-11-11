## Story
As a business member, I want to see only the conversations and messages of my business, one inbox per channel, so that the data of other businesses never mixes with mine.

## Acceptance criteria
- [ ] Given I am a member of the active business (any role), when I list the conversations of a channel (WhatsApp, Messenger or Instagram), then I see only the chats of that channel's accounts of my business, by latest activity, with the client's name, the last message, whether the 24-hour window is open and whether the bot is paused; never chats from another channel or another business; if my business has no accounts on that channel the list is empty; any other channel is rejected.
- [ ] Given a chat of my business, when I open its messages, then I see them in chronological order and can load older ones; if the account belongs to another business, the API answers as if it did not exist (404).
- [ ] Given an account I disconnected, when I list conversations or open messages, then its chats and its history no longer appear.

## Plan
- Two read-only queries per channel, open to any member of the active business: the list of conversations and the messages of one chat.
- The scope comes from the connected accounts of the active business; the chats and messages are read by `wanps.inbox`, not reimplemented.
- Accounts are identified with the same id the account list shows, and an optional filter shows a single account when the channel has several.
- Paging follows `wanps.inbox`: by amount and offset for chats, and "older than" for messages.
- An account that is not the active business's is treated as missing, and a business without accounts on the channel gets an empty list.

## Out of scope
- Replying as a person (new story A).
- Pausing and resuming the bot (new story B).
- Receiving new messages live, without reloading or polling (new story C, with WebSockets).
- Searching, filtering by text or marking chats as read.
- Sending templates or messages outside the 24-hour window.

## Decisions made
- Every role can read for now: agents, supervisors and admins work the inbox. Revisit with #7 (permissions per role).
- Each channel has its own inbox and the channel is part of the route: no endpoint mixes channels (business rule 10).
- No inbox connections are stored: the scope is computed on each request from the active business's connected accounts. With no accounts, `wanps.inbox` would return the messages that have no account (single-business mode), so a business with no accounts on a channel must get an empty list instead.
- Accounts show the same id as in the account list, never the internal id of `wanps-core`.
- Live updates are not polled: the frontend loads the history through this API once and receives new messages through WebSockets (story C).
