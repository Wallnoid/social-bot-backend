## Story
As a business member, I want to search and filter the contacts by name, phone, stage, tag or person in charge, so that I find quickly who I need.

## Acceptance criteria
- [ ] Given contacts of my business, when I search by a piece of a name or phone, then I only get the contacts that match, whatever the capitalization.
- [ ] Given contacts with stages, tags and people in charge, when I filter by stage, by one or several tags, or by person in charge (or "nobody in charge"), then I only get the contacts that match, and several filters together narrow the result.
- [ ] Given a stage, tag or person that is not from my business, when I filter by it, then I get a validation error, and a search that matches nothing returns an empty list.

## Plan
- The list takes optional search text and filters for tags and person in charge, besides the stage it already has; all of them combine, and paging and order stay as they are.
- The search looks in the name the team sees (the name written by the team, else the channel's) and in the phone, with partial matches.
- Several tags narrow the result: a contact must have all of them. Filtering by person in charge accepts one member of the business or "nobody".
- The stage, the tags and the member are validated against the active business.
- Tests: each filter alone, combined, case and partial match, several tags, another business's data not leaking, and invalid values.

## Out of scope
- Searching by email, company or the text of the messages or notes.
- Filtering by several people in charge or several stages at once, sorting options and saved filters.
- Counting results per filter.

## Decisions made
- The phone is searched with partial matches, like the name.
- Several tags mean "has all of them" (they narrow, like the other filters).

## Suggestions (your call)
- None.
