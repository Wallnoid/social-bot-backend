## Story
As a business member, I want to see my business's connected channel accounts, and as an admin edit them, without ever seeing their secrets, so that the app shows the right inboxes and admins can keep the accounts up to date safely.

## Acceptance criteria
- [ ] Given I am a member of the active business (any role), when I list the channel accounts, then I see only my business's accounts with their channel, name, ids and whether they are active, and never their access token.
- [ ] Given I am an admin of the active business, when I change an account's name or replace its access token, then the change is saved, the response never contains the token, and the new token is stored encrypted; agents and supervisors are rejected.
- [ ] Given an account that belongs to another business, when I try to edit it, then the API answers as if it did not exist.

## Plan
- A list of the active business's accounts, for any member, built from the business–account link from #8 and reading the data from wanps-core's account.
- Editing one account of the active business, for admins only: name and access token; the channel, the external id, the business id and the Meta App cannot change.
- The response uses the same shape as connecting an account (no token), so the frontend reuses it.
- An account outside the active business is looked up as missing, never as forbidden, so it does not reveal that it exists.

## Out of scope
- Disconnecting an account and connecting it again afterwards (#14).
- Turning the bot on or off (`is_active`) and configuring it (handler, prompt, AI).
- Changing the channel, the external id, the business id or the Meta App of an account.
- Checking the new token with Meta.
- Pagination: a business has few accounts.

## Decisions made
- Every role can list the accounts for now: the frontend's sidebar needs the business's channels for any user. Revisit with #7 (permissions per role).
- The business id is not editable: if Meta moves a number to another WhatsApp Business Account, the account is disconnected and connected again (#14).
- Disconnecting is its own story (#14), because a disconnected account must be connectable again despite soft delete.
