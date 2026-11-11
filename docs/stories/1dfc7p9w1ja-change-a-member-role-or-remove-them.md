## Story
As a business admin, I want to change a member's role or remove them from my business, so that access matches what each person should do.

## Acceptance criteria
- [ ] Given I am an admin of the active business, when I view its members, then I see everyone except myself, and when I change one's role, that person works with the new role from their next request.
- [ ] Given I am an admin of the active business, when I remove a member, then that person loses access to that business from their next request and keeps their account and their other businesses.
- [ ] Given I am an agent or supervisor, or the member belongs to another business, or the member is myself, when I try to change or remove them, then the API rejects it.

## Plan
- A list of the active business's members with their id, name, email and role, for admins only and without the admin who requests it.
- Changing a member's role and removing a member, for admins of the active business only.
- A removed member can be invited again.
- Access and role are already checked on every request, so changes apply immediately without touching login.
- Two admins acting on each other at the same time cannot leave the business without an admin.

## Out of scope
- Permissions by role in the rest of the API (#7).
- Cancelling pending invitations (#12).
- Notifying the member by email about the change.
- Restoring a removed member: they are invited again.
- Leaving a business on your own.

## Decisions made
- The member list is included, because without it an admin cannot tell who to change.
- An admin cannot change or remove themselves, and does not appear in the list they request.
- An admin can change or remove another admin: the rules do not tell admins apart and there is no owner role.
- Removing or demoting an admin cancels every pending invitation they sent in that business, so they cannot come back through one of them; a person they invited in good faith must be invited again.
- There is no separate last-admin rule: since the admin acting always stays an admin, the only way to lose the last one is two admins acting on each other at once.
