## Story
As a business member, I want to see the contacts in the stages of the pipeline (New, In conversation, Interested, Client, Lost) and move them between stages, so that I follow where each client is.

## Acceptance criteria
- [ ] Given my business, when I (any role) open the pipeline, then I see its stages in order (New, In conversation, Interested, Client, Lost by default), each with how many contacts it has, and I can page the contacts of each stage with the same data as the contact list, latest contact first.
- [ ] Given a contact (new or existing before this story), when I look at it in the pipeline, the list or its file, then it is in "New" until someone moves it; when I move it to any other stage, then it shows in that stage everywhere.
- [ ] Given a stage of another business or one that does not exist, when I try to move a contact there, then I get a validation error and the contact stays where it was.

## Plan
- Stages stored per business, in order; every business (new and existing) gets the five default ones.
- Each contact has a stage; new contacts and the ones already there start in the first stage ("New").
- An endpoint lists the stages of the active business in order, with their contact counts; the contact list takes a stage filter so each column pages on its own.
- The stage is moved with the existing contact edit (PATCH), validated against the stages of the active business; list and file show the stage.
- Tests: default stages for new and existing businesses, counts, the stage filter, moving, a stage of another business, and isolation.

## Out of scope
- Creating, renaming, reordering or deleting stages (story 5).
- Moving the stage from a chat of the inbox (story 6).
- Manual order of contacts inside a stage, transition rules, and history of stage changes.
- Real-time event when a contact changes stage.

## Decisions made
- Stages are stored per business from now on (not a fixed list in code), so story 5 only adds editing.
- Every contact starts in "New", including the ones that existed before this story.
- Inside a stage, contacts are ordered by last contact, as in the list.
- Each stage carries its contact count, for the column headers of the board.
- Any member moves any contact from any stage to any other; there are no transition rules yet.

## Suggestions (your call)
- None.
