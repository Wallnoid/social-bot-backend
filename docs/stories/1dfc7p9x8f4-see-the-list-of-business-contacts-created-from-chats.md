## Story
As a business member, I want to see the list of the contacts of my business, created by themselves from the first message of each chat (also the chats that already exist), with their name, channel and last contact, so that I have my clients in one place.

## Acceptance criteria
- [ ] Given the first message of a chat of a channel account of my business is saved (sent by the client or by the business), when it arrives, then a contact for that chat appears in the contact list of my business, only once no matter how many more messages come, and saving the message never fails because of it.
- [ ] Given my business already had chats before the CRM existed, when the contact list is opened for the first time, then every one of those chats already has its contact, with no action from anyone.
- [ ] Given I am a member (any role) of the active business, when I open the contact list, then I see only the contacts of my business, each with its name (or "Messenger user" / "Instagram user" while Meta has not given it, and on WhatsApp an empty name with the phone beside it, as the inbox does), its channel and the date of its last contact, the most recent first and paginated; a member of another business never sees them.

## Plan
- New CRM app with a contact that belongs to a business and points to one chat (channel account + client id on that channel); one contact per chat, enforced by the database.
- Create the contact when a chat's first message is saved, hooking into the same "message saved" point the inbox already uses for real time, and guarded so a failure there never breaks the message.
- A one-time data step that creates the contacts of the chats that already exist.
- Name follows the chat (the name the channel gives, with the same fallback the inbox uses); last contact is taken from the chat's latest message in either direction, not kept as a copy.
- One read-only list endpoint under the API, scoped by the active business and open to every member; tests for creation, no duplicates, the backfill, isolation between businesses and ordering.

## Out of scope
- The contact file, its conversations and editing its data (stories 2 and 3).
- Pipeline stages, notes, tags, assignment, search and filters (stories 4–10).
- Merging contacts across channels (story 11).
- Creating contacts by hand, importing and exporting.
- Real-time updates of the contact list.

## Decisions made
- Last contact is the latest message of the chat, from the client or from the business.
- A chat started by the business (for example a WhatsApp template to a new number) also creates its contact.
- Contacts of a disconnected channel account stay in the list: the client is still a client of the business.
- In this story the name is always read from the chat, so a name Meta gives later shows by itself; once story 3 lets the team edit it, the edited name wins.
- A WhatsApp contact without a name (for example a chat the business started with a template) keeps the name empty and the list gives its phone (`contact_id`), the same rule the inbox already follows; the frontend shows the phone. Both screens take the name from one shared rule. Decided after the code review.

## Suggestions (your call)
- Reuse the inbox's "Messenger user" / "Instagram user" fallback instead of a second copy, so the two screens never disagree.
