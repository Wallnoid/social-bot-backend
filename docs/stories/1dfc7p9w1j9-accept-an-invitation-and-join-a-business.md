## Story
As an invited person, I want to accept the invitation and join with a new or existing account, so that I can work in that business.

## Acceptance criteria
- [ ] Given a valid link and I have no account, when I accept with my name and a valid password, then my account is created and I join the business with the invitation's role.
- [ ] Given a valid link and I already have an account, when I accept while logged in with the invited email, then I join the business with that role; with a session from another account, it is rejected.
- [ ] Given a link that is expired, already used, nonexistent, from a deleted business or for a deactivated user, when I try to accept, then it is rejected with the same message and no membership is created.

## Plan
- With the token from the link, the frontend looks up the business, the role, the email and whether that person must create an account or log in.
- A single accept action covers both cases: new account or logged in with the invited email.
- Accepting is atomic: it creates the account if needed and the membership, and marks the invitation as used, so a double click cannot use it twice.
- Accepting cancels the other invitations of that email in that business.
- Looking up and accepting are public, so they have a rate limit.

## Out of scope
- Cancelling a pending invitation (#12).
- Suspended businesses (#11).
- Permissions by role in the rest of the API (#7).
- Resending an expired invitation.

## Decisions made
- An existing account must be logged in with the invited email to accept: a forwarded email is not enough to add it to a business.
- A used invitation is marked with soft delete, with no migration; "accepted" and "cancelled" are not told apart.
- A new account is not left logged in: the person logs in normally, as in #13.
- The invited person chooses the password, with confirmation and the same validations as the first admin, but in the same accept step and with no second email.
- An existing account with no password creates it when accepting with this link, and keeps its name.
