## Story
As a business admin, I want to invite a person by email with a role (agent, supervisor or admin), and have the invitation expire after one week, so that my team can access the business without leaving invitations open forever.

## Acceptance criteria
- [ ] Given I am an admin of the active business, when I invite an email with a role, then that person receives an email with a link to join that business with that role, stating when it expires (7 days by default).
- [ ] Given I am an agent or supervisor of the active business, when I try to invite someone, then the API rejects it.
- [ ] Given the email is already a member of that business or already has a pending invitation in it, when I invite it, then the API rejects it with a clear message.

## Plan
- An invitation record per business with email, role, who invited, a single-use token and the expiry date, calculated from a value in `.env` (7 days by default).
- An endpoint for the admin of the active business (`X-Tenant-ID`) that validates the email and role, creates the invitation and sends the email with the link `{FRONTEND_URL}/accept-invitation?token=…`.
- Only an admin of the active business can invite; agent and supervisor get a rejection.
- Inviting someone who is already an active member or has a non-expired pending invitation in that business is rejected.
- If the email cannot be sent, the API responds with an error and the invitation is not saved.

## Out of scope
- Accepting the invitation, with a new or existing account (#5).
- Cancelling a pending invitation (#12).
- Listing the business's pending invitations.
- Resending an expired invitation.
- Permissions by role in the rest of the API (#7): here it only checks that the inviter is an admin.

## Decisions made
- The expiry is configurable in `.env`, with 7 days by default.
- Inviting an active member or an email with a non-expired pending invitation is rejected.
- No email sent means no invitation: an invitation nobody received is useless.
