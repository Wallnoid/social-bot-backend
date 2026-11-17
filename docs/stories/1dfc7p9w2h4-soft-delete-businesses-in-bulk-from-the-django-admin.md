## Story
As a Social Bot team member, I want deleting businesses (one or many) from the Django admin to be a soft delete I can undo, so that a mistake never loses a business, its team or its history.

ClickUp: 1dfc7p9w2h4

## Acceptance criteria
- [ ] Given one or more businesses selected in the admin, when the team uses "Delete selected" and confirms, then they are marked as deleted, they are not removed from the database, and their members, invitations, accounts and history are kept.
- [ ] Given a deleted business, when the team looks for it in the admin, then it finds it with a filter of deleted ones and can restore it, and its members get in again as before.
- [ ] Given the shared Meta App, when it is deleted from its list, then it is a soft delete too.

## Plan
- The admins of soft-deleted models delete in bulk with a soft delete, as the button that deletes one does.
- The list of businesses also shows the deleted ones, with a filter by state, and a "Restore" action.
- Memberships, invitations and accounts are not touched when deleting, so restoring the business gives everything back.
- Tests: deleting several in bulk, the related data kept, a member not getting into a deleted business and getting in again after restoring it, the filter, and the Meta App.

## Out of scope
- Deleting businesses for real (purging old ones).
- The text of Django's confirmation page, which says the related objects "will be deleted": misleading, but changing it needs a template of our own.
- Users (`User`), which have no soft delete.

## Decisions (agreed)
- The memberships of a deleted business are not touched: they already give no access (the active business, the profile, the real time and the bot skip deleted businesses), and so restoring is exact.
- Restoring is a "Restore" action in the list, like "Reactivate"; the form shows the deletion state as read only, so there are not two ways to do the same.
- The scope is the businesses and the shared Meta App, the two admins that delete for real today; channel accounts already have deleting turned off.
- It is only in the Django admin: the API already treats a deleted business as gone, so the frontend changes nothing.
