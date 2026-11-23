## Story
As a business member, I want to open the file of the contact from a chat of the inbox and move it of stage there, so that I do not leave the conversation.

## Acceptance criteria
- [ ] Given a chat of my business open in the inbox, when I (any role) look at it, then I get its contact with its current stage, so I can open its file; a chat whose contact does not exist gets none.
- [ ] Given that contact, when I move it to another stage from the chat, then the chat, the pipeline, the list and the file show the new stage.

## Plan
- The messages of a chat come with its contact (id and stage), looked up by the account and the client of the chat within the active business.
- Opening the file and moving the stage reuse the existing contact file and edit; nothing new there.
- Tests: the chat brings its contact and stage, a chat without a contact brings none, moving from the chat shows in the chat and the pipeline.

## Out of scope
- The stage in the list of chats of the inbox.
- Real-time event when a contact changes stage.
- Editing other data of the contact from the chat (it is the same edit of the file).

## Decisions made
- The bridge from a chat to its contact is in the messages of the chat (what loads when it opens), not in the list of chats nor a new endpoint.

## Suggestions (your call)
- None.
