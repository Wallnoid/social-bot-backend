## Story
As a business admin, I want to disconnect a channel account of my business, so that its messages stop arriving and I can connect it again later.

## Acceptance criteria
- [ ] Given I am an admin of the active business, when I disconnect one of its accounts, then it no longer appears in the list of accounts, the bot does not reply to it, its new messages are no longer stored, and its token is no longer kept.
- [ ] Given an account I disconnected, when I connect it again with the same data, then it is connected as a new, empty account, without an "already connected" error.
- [ ] Given I am an agent or supervisor, or the account belongs to another business, when I try to disconnect it, then the API rejects me (403) or answers as if it did not exist (404) respectively, and the account stays as it was.

## Plan
- An action to disconnect an account of the active business, for admins only; an account of another business is treated as missing.
- On disconnect, the `wanps-core` account is archived: it is turned off, its token is erased and its id is freed so its messages are ignored and the same number can be connected again. Its message history stays in the database.
- The link to the business is soft-deleted, so the account disappears from the list.
- Connecting again reuses the flow from #8 unchanged: it creates a new account.

## Out of scope
- Seeing, exporting or recovering the history of a disconnected account.
- Removing the number or page from Meta (webhook subscription): the admin does that in Meta.
- Disconnecting several accounts at once, or disconnecting when a business is suspended (#11).
- Undoing a disconnection.

## Decisions made
- `wanps-core` accounts cannot be deleted: their messages and conversations reference them with `PROTECT`. Disconnecting archives the account instead.
- The webhook looks accounts up by channel and id without checking `is_active`, so an inactive account would keep storing messages. Freeing its id is what makes its events be ignored.
- Reconnecting starts empty: another business that later connects the same number does not inherit chats that are not theirs. The old history stays in the database but is not visible in the app.
- The token is erased on disconnect: it is no longer needed and it is one less stored secret.
