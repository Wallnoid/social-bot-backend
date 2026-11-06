## Story
As a business member, I want to reply to a conversation as a person from the inbox, so that my clients get an answer from my team.

## Acceptance criteria
- [ ] Given a chat of my business with the 24-hour window open, when I send a text, then it reaches the client from that account, it appears in the chat's messages as an outgoing message with my name, and the bot is paused in that chat so it does not reply on top of me.
- [ ] Given the 24-hour window is closed, or Meta rejects the message, when I send a text, then the API answers with a clear error and the message does not appear as sent.
- [ ] Given the account belongs to another business or is disconnected, or the text is empty, when I try to send, then the API rejects it (404 or 400) and nothing is sent.

## Plan
- An action to send inside a chat of each channel, open to any member of the active business, with the account required as when reading the messages.
- The sending is done by `wanps.inbox` (24-hour window, sending from the account, message stored), limited to the business's accounts as in #10.
- The sender is the member's name, and the bot is paused in that chat until it is resumed.
- Errors are translated to the API format: window closed (409), Meta rejection (502), account of another business or disconnected (404), empty text (400).
- The sent message is returned with the same shape as the chat's messages, so the frontend can add it without reloading.

## Out of scope
- Replying outside the 24-hour window: WhatsApp templates and the human-agent tag (story D).
- Sending images, files, buttons or lists.
- Resuming the bot (story B) and seeing messages live (story C).
- Editing or deleting sent messages, and "typing" indicators.

## Decisions made
- Every role can reply: according to the business rules, the agent is the one who answers conversations.
- The bot is always paused when a person replies, with no option to keep it on. Until story B exists, it is resumed from the Django admin.
- The sender shown is the member's full name, or their email when they have none.
- A person can reply from an account whose bot is off: every account starts inactive (`is_active: false`), and that only turns off the bot, not people.
