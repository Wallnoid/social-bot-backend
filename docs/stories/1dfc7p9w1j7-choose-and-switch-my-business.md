## Story
As a user who belongs to several businesses, I want to choose and switch the business I work in, so that I see only that business's data.

## Acceptance criteria
- [ ] Given I belong to several businesses, when I indicate in a request which one I want to work with, then the API works in that business and shows me which one it is and my role in it; if I indicate another, it works in the other.
- [ ] Given I indicate a business I do not belong to, was removed from or that was deleted, when I make the request, then the API rejects it as if that business did not exist.
- [ ] Given I belong to several businesses and indicate none, when I make the request, then the API asks me to choose one (and if I belong to only one, it works in that one without me indicating it).

## Plan
- The frontend indicates the active business in each request with a header (`X-Tenant-ID`). Switching business means sending another id; nothing is stored on the server.
- On each request the backend checks that the user has an active membership in a business that is not deleted; if not, it responds as if it did not exist.
- The active business and the user's role stay available to the rest of the API, so the following stories can filter their data with them.
- A minimal endpoint (`GET /api/v1/tenants/current/`) returns the active business and my role, to verify the mechanism end to end.
- API-level tests: chosen business, another business, a foreign, removed or deleted business, none indicated with several, and with only one.

## Out of scope
- Filtering real data by business (contacts, conversations, channels): it comes with #8 and #10, which will use this mechanism.
- Permissions by role (#7).
- Suspended businesses (#11): for now they behave like any other.
- Remembering the last business used between sessions.

## Decisions made
- The active business goes in the `X-Tenant-ID` header (not in the JWT), so login stays untouched and two businesses can be open in two tabs.
- With several businesses and none indicated, the API responds with an error asking to choose; it never picks one by default.
- The minimal endpoint is its own (`tenants/current/`), not part of `/me`.
