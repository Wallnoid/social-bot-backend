## Story
As a business admin, I want to cancel a pending invitation, so that a person invited by mistake cannot join my business.

## Acceptance criteria
- [ ] Given I am an admin of the active business, when I view the pending invitations and cancel one, then its link stops working and I can invite that email again.
- [ ] Given I am an agent or supervisor, or the invitation belongs to another business, when I try to view or cancel them, then the API rejects it.
- [ ] Given the invitation was already accepted, cancelled or has expired, when I try to cancel it, then the API responds that it does not exist.

## Plan
- A list of the active business's pending, unexpired invitations, for admins only.
- Cancelling a pending invitation, for admins of the active business only.
- A cancelled invitation is treated like a used one: its link is rejected with the usual message.

## Out of scope
- Resending an expired invitation.
- Emailing the person that their invitation was cancelled.
- Seeing the history of accepted, cancelled or expired invitations.
- Permissions by role in the rest of the API (#7).

## Decisions made
- The list of pending invitations is included, because without it an admin cannot tell which one to cancel.
- Each invitation shows its email, role, who invited and when it expires, so an invitation made by mistake is easy to recognize.
- An admin can cancel another admin's invitations: the rules do not tell admins apart.
