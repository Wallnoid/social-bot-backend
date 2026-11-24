## Story
As a business member, I want to merge two contacts that are the same person on different channels, so that a client has a single file with all their chats.

## Acceptance criteria
- [ ] Given two contacts of my business, when I merge one into the other, then the contact that stays shows the chats of both in its file, keeps the notes and tags of both, and the other contact no longer appears in the list or the file.
- [ ] Given a merge, when the data of both differs, then the contact that stays keeps its name, phone, email, company, stage and person in charge, and what it had empty is filled from the other one; and when a client of a merged chat writes again, then the message goes to the contact that stays.
- [ ] Given a contact of another business, one that does not exist, or the same contact twice, when I try to merge, then I get a validation error and nothing changes.

## Plan
- A contact can have several chats: each chat points to its contact, and the contacts that already exist keep the one they had.
- Merging moves the chats, notes and tags of the contact that goes into the one that stays, fills its empty data, and deletes the other one, all in one step with the contact locks the project already uses.
- New messages of any chat find their contact through that link, so a merged chat never brings the deleted contact back.
- The file and the inbox show every chat of a contact; the list and the stage counts count a merged contact once.
- Tests: merge with each role, data and stage rules, notes and tags kept, a new message after the merge, other-business and invalid cases, and the old contacts migrating with their chat.

## Out of scope
- Undoing a merge or separating a chat.
- Choosing field by field which data wins, or a preview before merging.
- Suggesting duplicates automatically.
- Merging contacts of different businesses.

## Decisions made
- Any member can merge contacts, like the rest of the CRM.
- Two contacts of the same channel can be merged.
- The contact that stays wins; what it has empty is filled from the other one. Tags and notes are added together. If only the deleted contact has a person in charge, the one that stays takes it.
- One story, not split: the chats of a contact and the merge go together.

## Suggestions (your call)
- None.
