## Story
As a business admin, I want to log in and see which business I am working in and my role, so that I know I am in the right place.

## Acceptance criteria
- [ ] Given I belong to a business, when I log in and request my profile, then I see that business's name and my role in it.
- [ ] Given I belong to several businesses, when I request my profile, then I see each one with my role in it, and none I do not belong to.
- [ ] Given I was removed from a business or that business was deleted, when I request my profile, then that business no longer appears.

## Plan
- Login does not change: the frontend logs in with JWT and then requests the profile.
- The user profile includes, read-only, the list of their businesses: id, name and their role in each one.
- The list comes only from their active memberships and from businesses that are not deleted.
- API-level tests: one business, several businesses with no leaks from others, and a deleted membership or business.

## Out of scope
- Choosing or switching the active business and filtering data by business (#3).
- Suspended businesses (#11): for now they appear like any other.
- Permissions by role (#7).
- Business data beyond id, name and role (industry, description).
- Limiting the list to admins: it applies to any member (agent, supervisor or admin).

## Suggestions (your call)
- The list goes inside `/me` (a single call after login); #3 can read from the same place.
