## Story
As a business member, I want to see the name of the client in my Messenger and Instagram conversations, like I already do in WhatsApp, so that I know who I am talking to instead of seeing an empty name.

## Acceptance criteria
- [ ] Given a client writes for the first time to a connected Messenger page or Instagram account, when the message arrives, then the client's name is asked to Meta with the account's token and saved as the contact name, so the inbox shows it in the conversation list and in the messages.
- [ ] Given Meta does not give the name (the app is not allowed to read that profile, the token cannot read it, or Meta fails), when the message arrives, then the message is saved anyway and the inbox shows "Messenger user" or "Instagram user" instead of an empty name. The fallback is not saved as the real name.
- [ ] Given a conversation was shown with the fallback, when the same client writes again and Meta now gives the name, then the real name replaces the fallback from then on.
- [ ] Given the profile cannot be read, when many messages arrive, then Meta is not asked again for every single message (a failed lookup is not retried on each one), and receiving messages is never slowed down or blocked by the lookup.
- [ ] Given the name was already saved for a client, when they write again, then Meta is not asked again.
- [ ] The profile picture is out of this story; nothing about it is saved or returned.

## Plan
- The change lives in `wanps-core` (Messenger and Instagram webhook handling), not in this repo: the rule is not to reimplement here what `wanps-core` provides. Social Bot only upgrades the pinned release.
- Ask the Graph API for the profile of the client (`first_name` and `last_name` on Messenger, `name` and `username` on Instagram) with the account's token, only when the contact has no saved name.
- Run the lookup outside the request that Meta waits for, and give it a short timeout, so a slow Meta never makes the webhook fail or time out.
- Keep the fallback out of the database: the inbox answers "Messenger user" / "Instagram user" while the name is empty.
- Tests in `wanps-core`: name saved, Meta refuses the profile (fallback, message saved), Meta fails or times out, name already known (no call), real name replaces the fallback, no repeated calls after a failure.
- In this repo: bump `wanps-core` to the new release and add one inbox test that a Messenger conversation without a name shows the fallback.

## Out of scope
- The profile picture.
- Asking Meta for the advanced permission or the App Review that reads profiles of any client (done in Meta's panel, not in code; see the "Human Agent" card for how those requests go).
- Merging the same person across channels (still undecided in the business rules).
- Names for WhatsApp, which already arrive in the webhook.

## Decisions made
- The fallback texts are "Messenger user" and "Instagram user" until the name is known.
- While the Meta App is in development mode, Meta only gives the profile of people with a role in the app (admins, developers, testers). For any other client the fallback is what will show until the permission is approved in Meta.
- The fallback is shown, not stored, so a later successful lookup fixes the name without any cleanup.

## Open points
- Where exactly the fallback is applied (the `wanps.inbox` services or this backend's serializers) is decided when the plan is checked against the code of `wanps-core`.
