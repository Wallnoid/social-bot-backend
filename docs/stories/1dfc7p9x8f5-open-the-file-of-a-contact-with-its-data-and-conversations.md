## Story
As a business member, I want to open the file of a contact and see its data and its conversations, so that I know who it is and what we talked about.

## Acceptance criteria
- [ ] Given a contact of my business, when I open its file (any role), then I see its name (with the same rule as the list), its id on the channel (the phone on WhatsApp), its channel, the channel account it writes to, the date of its first contact and the date of its last contact.
- [ ] Given I open the file, when I look at its conversations, then I see each chat of the contact (one today) with its account, its last message and what is needed to open its messages in the inbox; if the account is disconnected, the chat is marked as disconnected and cannot be opened.
- [ ] Given a contact of another business, or one that does not exist, when I try to open its file, then I get "not found", without learning whether it exists.

## Plan
- A contact detail endpoint next to the list, scoped by the active business and open to every member.
- The data comes from the contact and its chat, with the same name and last contact rules the list already uses (reused, not copied).
- The conversations of the contact come as a list; each one carries the business channel account, the channel, the client id, the last message and whether the account is connected. The messages are read with the existing inbox endpoint.
- Tests: the data of the file, the conversation with its last message, a disconnected account, isolation between businesses and a contact that does not exist.

## Out of scope
- Editing the data of the contact (story 3).
- Reading the messages of a disconnected account.
- Pipeline stage, notes, tags and person in charge (stories 4, 7, 8 and 9).
- Opening the file from a chat of the inbox (story 6).
- Merging contacts (story 11).

## Decisions made
- The file does not carry the messages: the frontend opens the chat with the existing inbox messages endpoint, which already pages them and serves their files.
- A chat of a disconnected account is shown marked as disconnected, without messages; making that history readable is left for another story if needed.
- The conversations come as a list even though a contact has one chat today, so the frontend does not change when story 11 merges contacts.
- The first contact is the date of the first message of the chat, not when the contact was created, so contacts loaded from existing chats show the real date.
- The whole file (name, dates and last message) reads only the chat of the account's channel, as the inbox does.
- A contact whose account lost its link to the business for good answers "not found". Decided after the code review.

## Suggestions (your call)
- Move the name and last contact calculation that lives inside the list view to a shared function, because the file needs it the same way (both endpoints would use the same subqueries).
