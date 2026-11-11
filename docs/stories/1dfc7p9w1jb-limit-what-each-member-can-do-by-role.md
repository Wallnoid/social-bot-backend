## Story
As a business member, I want what I can do to depend on my role (agent, supervisor or admin), so that each person only does what their role allows.

## Acceptance criteria
- [ ] Given I am an agent, when I use the inbox (read, reply, pause or resume the bot, open files, connect in real time), then it works; when I try to list the members or manage members, invitations or channel accounts, then I get 403.
- [ ] Given I am a supervisor, when I do what an agent does or list the members of the business, then it works; when I try to invite, cancel invitations, change roles, remove members or connect, edit or disconnect channel accounts, then I get 403.
- [ ] Given I am an admin, when I do anything a supervisor does or manage members, invitations and channel accounts, then it works.

## Plan
- One table of what each role can do, kept in one place, instead of checking the role in each view.
- One reusable permission for "supervisor or higher", next to the existing admin one.
- Apply it to the endpoints that need it (today only the list of members).
- One test per role and endpoint that shows the whole table, and a test that fails if an API endpoint does not declare its permissions.

## Out of scope
- Agents seeing only the conversations assigned to them (there is no assignment yet).
- Closing the open sockets of someone whose role changes.
- Permissions for contacts, pipeline and appointments (they do not exist yet).

## Decisions made
- Agent: the whole inbox. Supervisor: the same, plus reading the list of members. Admin: everything, including managing members, invitations and channel accounts.
- The list of channel accounts stays open to any member: the inbox needs it to show the numbers and pages.
- The list of pending invitations stays admin-only; the supervisor only reads the members.
- Most of the table already existed and had tests (channels, invitations, member changes, bot); the only behavior change is the list of members for supervisors.
