## Story
As a business member, I want the new messages, their delivery states and the changes of the bot to appear in my inbox instantly, without reloading or asking every few seconds, so that I can answer my clients at the moment.

## Acceptance criteria
- [ ] Given a signed-in member, when they ask the API for a connection permit and open the permanent connection with it, then they are connected to their business; a false, expired or already used permit, or none at all, rejects the connection.
- [ ] Given a connected member, when a message arrives from a client, one goes out from an account (from a person or from the bot), its delivery state changes, or the bot is paused or resumed in a chat of their business, then they receive an event with what is needed to update that chat (channel, account, contact and the message or the bot state), and they never receive events of another business.
- [ ] Given a member connected to an account, when another person of the same business replies from another browser, then they also see that outgoing message instantly.

## Plan
- One permanent connection (WebSocket) per user, with one group per business; the events are delivered through Redis so they arrive from any process (web or worker).
- An endpoint of the normal API gives a short-lived, single-use connection permit, tied to the user and to the active business; the permanent connection exchanges it when it opens.
- The signals that wanps-core already sends (new message, delivery state, bot) are listened to, and each one becomes an event for the group of the business that owns the account.
- The event carries the message in the same shape the chat read already returns, so the frontend does not have to ask for it again.
- The server moves to ASGI so that HTTP and WebSockets are served by the same process, and the proxy must let the permanent connection through.

## Out of scope
- Recovering what was lost while disconnected: on reconnecting, the frontend asks for it with the existing read endpoints.
- "Typing…" notices, presence (who is connected) and read receipts.
- Push or email notifications, and unread counters.
- Closing the connection of someone who stops being a member at that very moment: it applies when they reconnect.
- Frontend changes.

## Decisions made
- The library is Django Channels, with `channels-redis` to deliver the events between processes. They are new dependencies (`channels`, `channels-redis`, `uvicorn`, `uvicorn-worker`); the user is told before they are installed.
- The ASGI server is Uvicorn running under Gunicorn (only the worker type of Gunicorn changes), so the process management that Gunicorn gives is kept. In development the app is run with `uvicorn ... --reload` instead of `runserver`.
- The event carries the whole message (with its text and file mark), in the shape of the chat read. Only authenticated members of the business that owns the account receive it.
- The connection permit is single-use and short-lived (seconds) and travels in the opening of the connection; the access token is not put in the address, where it would be logged.
- Any member of the business can connect and receives the events of all its accounts and channels; each event says its channel and the frontend shows the inbox of the channel the person is in (rule 10 of the business rules: there is no unified list).
- The API also runs inside the ASGI server. It is tested together. If the WebSockets grow a lot, they can move to their own container without changing the code.
- The proxy of the VPS must pass `Upgrade` headers for the permanent connection; that is infrastructure, outside the repo.

## Suggestions (your call)
- If a single connection per business turns out to be too much traffic, the events can later be filtered by the account the person has open.
