## Story
As a business admin, I want to create, rename, reorder and delete the stages of the pipeline of my business, so that it fits how my business sells.

## Acceptance criteria
- [ ] Given I am an admin, when I create a stage with a name, then it is added at the end of the pipeline with no contacts.
- [ ] Given I am an admin, when I rename a stage, then the new name shows everywhere (pipeline, list, file).
- [ ] Given I am an admin, when I send the full list of the stages of my business in a new order, then the pipeline shows them in that order, and new contacts start in the stage that is now first; a list that is not exactly the stages of my business gives a validation error and changes nothing.
- [ ] Given I am an admin, when I delete a stage without contacts, then it is gone; when it has contacts, I must say which other stage of my business they move to, else I get a validation error and nothing changes; the last stage of the business cannot be deleted.
- [ ] Given a name already used by another stage of my business (whatever the capitalization), when I create or rename a stage with it, then I get a validation error.
- [ ] Given I am an agent or a supervisor, when I try any of these, then I get 403; given a stage of another business, I get 404 and it does not change.

## Plan
- `POST /api/v1/crm/stages/` (admin) creates a stage after the last one; `GET` stays for any member.
- `PATCH /api/v1/crm/stages/<id>/` renames and `DELETE /api/v1/crm/stages/<id>/?move_to=<id>` deletes (soft delete), moving its contacts first; both admin only.
- `PUT /api/v1/crm/stages/order/` takes `{"stages": [ids in order]}` and rewrites every position in one transaction.
- Names unique per business ignoring case, validated in the serializer (deleted stages do not count).
- Tests: create, rename, reorder (and the new first stage), delete with and without contacts, the last stage, repeated names, roles and isolation.

## Out of scope
- A limit on the number of stages, colors or icons.
- Choosing an entry stage other than the first one.
- Transition rules, history of stage changes, real-time events.

## Decisions made
- Deleting a stage with contacts requires `move_to`, a different stage of the same business; without contacts it is not needed.
- The first stage is where new contacts start, so reordering changes it.
- Stage names are unique per business, ignoring capitalization.
- Reordering takes the full ordered list of ids, so positions never repeat.

## Suggestions (your call)
- None.
