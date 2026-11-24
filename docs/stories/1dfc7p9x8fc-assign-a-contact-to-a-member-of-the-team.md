## Story
As a business member, I want to assign a contact to a member of the team, so that it is clear who takes care of each client.

## Acceptance criteria
- [ ] Given a contact of my business with nobody in charge, when I (any role) assign it to a member of my business, then the list and the file show who is in charge; every contact starts with nobody in charge.
- [ ] Given a contact with a person in charge, when I assign it to another member or take the person off, then the change shows to everyone.
- [ ] Given a person who is not a member of my business or does not exist, when I try to assign a contact to them, then I get a validation error and the contact stays as it was.

## Plan
- Each contact has at most one person in charge, a member of the business; the contacts that already exist and the new ones start with nobody in charge.
- The person in charge is changed with the same contact edit that moves the stage: the member is sent (the `id` of the list of members) or an empty value to take them off, and it is validated against the members of the active business.
- The list and the file show the person in charge with their id and name; if that person leaves the business, the contact shows nobody in charge.
- Tests: assigning with every role, changing and taking off, a member of another business or one that does not exist, the contact not changing when it fails, and a member who leaves.

## Out of scope
- Notices when someone is assigned a contact, and automatic or round-robin assignment.
- Filtering contacts by person in charge (CRM 10).
- A history of assignments and several people in charge of one contact.
- Letting an agent see only the contacts assigned to them.

## Decisions made
- Any member assigns or takes off the person in charge of any contact, themselves or another member.
- The person in charge is sent with the `id` of the member (the one the list of members gives), and the same field empty takes them off.

## Suggestions (your call)
- None.
