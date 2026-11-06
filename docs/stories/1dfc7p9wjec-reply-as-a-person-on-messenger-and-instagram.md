## Story
As a business member, I want to reply as a person to a Messenger or Instagram client when more than 24 hours but less than 7 days have passed since their last message, so that I can follow up without waiting for them to write again.

## Acceptance criteria
- [ ] Given a Messenger or Instagram chat of my business whose 24-hour window is closed and whose client wrote less than 7 days ago, when I reply with the human-agent option, then it reaches the client from that account, appears in the chat as an outgoing message with my name, and the bot is paused in that chat.
- [ ] Given the client's last message is more than 7 days old, or the 24-hour window is closed and I do not use the option, when I try to reply, then the API answers with a conflict and a clear message that tells the two cases apart, and nothing is sent.
- [ ] Given the option is used on a WhatsApp chat, or the account belongs to another business or is disconnected, when I try to reply, then the API rejects it (400 or 404) and nothing is sent.

## Plan
- The send action accepts an optional human-agent flag, valid only on Messenger and Instagram; on WhatsApp it is rejected.
- The sending is done by `wanps.inbox`, which already checks the 24-hour and 7-day windows and sends with the human-agent tag; Social Bot only accepts the flag and keeps the business scope as for plain text.
- The conflict answers say which window failed: the 24-hour one (use the option) or the 7-day one (nothing can be sent), instead of the single message used today.
- The rest behaves as sending plain text: sender name, bot paused, errors in the API format, and Meta's rejection as the delivery error.
- The API documentation describes the new flag and the two conflict cases.

## Out of scope
- WhatsApp templates (story D).
- Sending images, audios or files.
- Showing in the chat list how long the human-agent window stays open: the frontend tries and handles the conflict.

## Decisions made
- The human-agent tag needs the "Human Agent" permission in Meta's App Review; without it Meta rejects the message and the API answers with the usual delivery error (502). It cannot be tested here, so the permission is requested by the Social Bot team in Meta.
- `wanps-core` already supports this, so no change is needed there.
- Every role can use it, as with plain text.
