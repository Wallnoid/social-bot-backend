## Story
As a Social Bot team member, I want to suspend and reactivate a business from the Django admin, so that I can cut off its access and its bot when needed (for example, when it does not pay) and give them back when it is solved.

ClickUp: 1dfc7p9w1jf

## Acceptance criteria
- [ ] Given a business suspended from the admin, when a member uses the app with that business (the API or the real time), then they are refused with a clear "business suspended" answer; the other businesses of the same user keep working.
- [ ] Given a suspended business, when a client writes to any of its accounts, then the message is saved, but the bot does not answer, the AI is not called and nothing is retried.
- [ ] Given a reactivated business, when its members and clients come back, then everything works as before: data, accounts, bot setup and history untouched.

## Plan
- The business keeps since when it is suspended (or nothing). The Django admin has the actions "Suspend" and "Reactivate", and shows and filters the state.
- When the active business is resolved, a suspended one is refused with its own error code. The profile of the user still lists it, marked as suspended, so the frontend can explain what happens.
- The real time refuses new permits and connections of a suspended business, and closes the open ones when it is suspended.
- The bot checks the state of the business before calling the AI, next to the other protections; the retries go through the same path.
- Tests: the API and the WebSocket refused with the code, another business of the same user untouched, the bot silent without AI, the reactivation and the isolation.

## Out of scope
- Suspending automatically for lack of payment (there is no billing yet).
- Telling the members of the business by email.
- Letting the business see why it was suspended or ask for the reactivation from the frontend.
- Pausing the Meta webhook: the messages are still saved.

## Decisions (agreed)
- A new state (`suspended_at`), not the soft delete: deleting means the business is gone, suspending means it is paused and comes back, and the frontend can say "suspended" instead of "not found".
- The business stays in the list of the user, marked as suspended, and using it answers 403 with the code `business_suspended`.
- The open WebSockets of the business are closed when it is suspended.
- No reason of the suspension is kept for now; the team can write it in the description of the business.
- The same check of the bot also covers soft-deleted businesses, which today still answer their clients and spend AI.
