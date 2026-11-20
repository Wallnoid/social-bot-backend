## Story
As a business member, I want to edit the name, phone, email and company of a contact, so that its file is right.

## Acceptance criteria
- [ ] Given a contact of my business, when I (any role) change its name, phone, email or company, then the file and the contact list show the new values, and the fields I did not send stay as they were.
- [ ] Given I clear the name I wrote, when I open the file or the list, then I see again the name the channel gives (same rule as today); phone, email and company can be cleared and stay empty.
- [ ] Given an invalid email, a phone with characters other than digits, "+", spaces or dashes, or a contact of another business or one that does not exist, when I try to save, then I get a validation error or "not found" respectively, and nothing changes.

## Plan
- Add name, phone, email and company to the contact, all optional and empty by default.
- A partial update (PATCH) on the existing contact detail endpoint, scoped by the active business and open to every member; it answers with the updated file.
- The name shown becomes: the one written by the team if any, else the channel name with today's rule; list and file both use it.
- File and list also return phone, email and company.
- Tests: partial edit, clearing the name falls back to the channel's, validation errors, isolation between businesses and a contact that does not exist.

## Out of scope
- Showing the edited name in the inbox (chat list and chat).
- Changing the channel id of the contact (it identifies the chat).
- Real-time event when a contact changes.
- Searching by these fields (story 10), merging contacts (story 11).
- History of who changed what.

## Decisions made
- The name written by the team takes priority over the channel name; clearing it shows the channel name again.
- The phone is a separate field, empty by default, even on WhatsApp; the channel id is never edited.
- The phone is free text (digits, "+", spaces and dashes), not strict E.164.
- Every member can edit, agents included.

## Suggestions (your call)
- None: the detail endpoint and the shared `contacts_of` query already cover what the edit needs.
