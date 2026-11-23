## Story
As a business member, I want to tag contacts (for example VIP or wholesaler), so that I can group them.

## Acceptance criteria
- [ ] Given a contact of my business, when I (any role) add a tag by its name, then the contact has it and it shows in the list and in the file; if the business had no such tag it is created, and if it already had one (ignoring capitalization) the same one is used.
- [ ] Given a contact with tags, when I remove one, then it no longer has it and the other contacts keep theirs.
- [ ] Given the tags of my business, when I list them, then I see them with how many contacts each has, to pick one when tagging; the ones of another business never show.

## Plan
- Tags belong to a business and their name is unique ignoring capitalization; a contact can have several.
- Tagging by name looks the tag up in the active business and creates it if it does not exist; adding one the contact already has does not duplicate it.
- The list and the file of a contact bring their tags, and there is a list of the tags of the business with their number of contacts.
- Everything is scoped to the active business: a contact or a tag of another business answers 404.
- Tests: tagging with every role, the same name with other capitalization, removing, not duplicating, list and file with tags, the tag list with counts, and isolation between businesses.

## Out of scope
- Renaming or deleting tags of the catalog, colors and icons.
- Filtering or searching contacts by tag (CRM 10).
- Tagging several contacts at once.
- A limit of tags per contact or per business.

## Decisions made
- Any member creates a tag by typing its name when tagging; the same name (ignoring capitalization) is the same tag.
- The name of a tag cannot be empty and has at most 50 characters.
- A tag without contacts stays in the catalog until a later story allows deleting it.

## Suggestions (your call)
- None.
