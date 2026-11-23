## Story
As a business member, I want to write internal notes on a contact, so that the team shares what it knows of the client.

## Acceptance criteria
- [ ] Given a contact of my business, when I (any role) write a note, then it is saved with me as its author and the time, and I see it in the notes of the contact.
- [ ] Given a contact with notes, when any member of the business opens its notes, then they see all of them, latest first and paged, each with its text, author and time; the clients never see them.
- [ ] Given a note, when its author edits or deletes it, then the change shows to everyone; when an admin deletes someone else's note, it is gone too; any other member gets 403.

## Plan
- Notes belong to a contact and its business; each keeps its author (a member) and its time.
- The notes of a contact are listed, created, edited and deleted under the contact, always scoped to the active business, so a contact of another business answers 404.
- The author comes from who is logged in, never from the body; a note cannot be empty.
- Tests: write and read with every role, order and paging, edit and delete by author and by admin, 403 for others, isolation between businesses.

## Out of scope
- Mentions, attachments, pinned notes, and a history of the edits of a note.
- Notifications when a note is written.
- Notes in the file of the contact or in the chat of the inbox (the notes have their own list).
- Searching or filtering by the text of the notes.

## Decisions made
- The author edits and deletes their own notes; an admin can also delete any note of the business; nobody else edits or deletes someone else's note.
- The notes have their own paged list under the contact, not inside its file.
- A note cannot be empty.

## Suggestions (your call)
- None.
