## Story
As a business member, I want a merged contact to show in the list and in the search according to all its chats, so that moving up the list and finding a client work as they did before the merge.

## Acceptance criteria
- [ ] Given a contact with merged chats, when the client of any of its chats writes, then the contact moves up the list and its last contact is the date of the latest message of all its chats.
- [ ] Given a contact with merged chats, when I search the name or the phone of any of its chats, then that contact is found, once, and the other filters (stage, tags, person in charge) still apply.

## Plan
- The last contact and the order of the list take the messages of the contact's own chat and of the chats of the contacts merged into it.
- The search by name and phone looks at the same set of chats and merged contacts.
- There is no new data and no migration, and a contact that was never merged behaves as it does today.
- Tests: order and date with a new message in a merged chat, search by the name and by the phone of a merged chat, appearing once, combining with the filters, and a contact without merges not changing.

## Out of scope
- The name shown: it stays the one of the contact that stays (the one the team wrote, else the one of its own chat).
- `first_contact_at` of the file and real-time events.
- Undoing merges.

## Decisions made
- The search counts everything of the merged contact: the name and the phone the team had written on it, the name the channel gives and the number of its chat.

## Suggestions (your call)
- None.
