## Story
As a Social Bot team member, I want to create a business with its first admin from the Django admin, so that a new client can start using the suite.

## Acceptance criteria
- [ ] Given I am in the Django admin, when I create a business with its name, its industry (from a predefined list), a description (industry and description are optional) and the email and name of its first admin, then the business exists and that person is a member with the admin role (with no password yet).
- [ ] Given the first admin's email already belongs to an existing user, when I create the business, then that same user becomes admin of the new business and no duplicate account is created.
- [ ] Given anyone, when they try to sign up through the API or to create, list or delete users of other businesses, then the API rejects it.

## Plan
- Add the business (tenant) and the membership that links a user to a business with a role (agent, supervisor or admin).
- In the Django admin, a form to create a business (name, industry from a predefined list and description) that also asks for the first admin's email and name, and creates the user or reuses the existing one.
- Show the business's members and their roles in the admin, read-only for now.
- Disable public sign-up and remove from the API the endpoints that list, create or delete users across all businesses.
- Tests: create with a new user, create with an existing user, and sign-up rejected.

## Out of scope
- The email with the link to create the password (separate story).
- Showing the business and role after logging in (#2), choosing or switching business (#3).
- Invitations (#4, #5, #12), suspending and reactivating (#11), channel accounts (#8).
- Self-service business sign-up.

## Suggestions (your call)
- A user with no password cannot get in until they use the link. The full walking skeleton (create a business and get in) is split between this story and the password link story, so it is best to do them back to back.
