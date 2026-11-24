## Story
As the Social Bot team, I want the WebSocket connection of the inbox to check where it comes from, so that only the Social Bot frontend can open it from a browser.

## Acceptance criteria
- [ ] Given a browser on a page that is not the frontend, when it opens `/ws/inbox/` with a valid permit, then the connection is rejected before it enters the inbox.
- [ ] Given the Social Bot frontend (one of the configured origins), when it opens `/ws/inbox/` with a valid permit, then it connects and gets the events as today; and in development, where CORS allows every origin, any origin connects.

## Plan
- The WebSocket route is wrapped with an `Origin` check that uses the same list of allowed origins as CORS (`CORS_ALLOWED_ORIGINS`) and lets everything pass when CORS allows every origin (development).
- The connection permit, its duration and the events do not change.
- Tests: a foreign origin rejected, the frontend origin accepted, development with open CORS accepted, and a rejection not spending the single-use permit.

## Out of scope
- Changing the connection permit or its duration.
- Changing the close with code 4403 of a suspended business.

## Decisions made
- A connection without an `Origin` header is rejected: browsers always send it, and the permit already needs a session. In development CORS is open, so tools still connect.

## Suggestions (your call)
- None.
