## Story
As a business member, I want to reply with an approved template to a WhatsApp client once the 24-hour window is closed, so that I can follow up with clients who stopped writing.

## Acceptance criteria
- [ ] Given a WhatsApp account of my business, when I ask for its templates, then I see the approved ones I can send from here (name, language, text and how many values it takes), and not the ones with variables in the header or in the buttons.
- [ ] Given a chat of my business, when I send an approved template with its values, then it reaches the client from that account, appears in the chat as an outgoing message with my name, and the bot is paused in that chat.
- [ ] Given the template does not exist, is not approved or takes another number of values, the client never wrote to that account, or the account belongs to another business or has no WhatsApp Business account id, when I try to send or list, then the API rejects it with a clear message and nothing is sent or stored.

## Plan
- First in `wanps-core` (version 0.4.1): a function that lists the approved templates of a WhatsApp account. Social Bot then raises its pinned version.
- In Social Bot, a query for the sendable templates of an account of the business, open to any member.
- Sending accepts a template (name, language and values) instead of the text, only on WhatsApp and only in chats that already exist; `wanps.inbox` does it, with the same bot pause as with text.
- Before sending, the template is checked against the listed ones (it exists, the language and the number of values) to give clear errors; Meta's rejections stay the usual delivery error.
- Errors and responses follow the format already used when sending text.

## Out of scope
- Starting new conversations with templates (marketing or notices to someone who never wrote).
- Templates with a header, images, documents or buttons with variables.
- Creating, editing or requesting approval of templates.
- Showing in the chat the real content of the template sent (for now only its name).
- Replying outside the window on Messenger and Instagram (story D2).

## Decisions made
- Only the templates that can be sent with what `wanps-core` already does are listed (variables only in the body).
- Templates are sent only to chats that already exist: a template does not check the window or whether a chat exists, so without this rule any member could write to any number from the business's account (spam, risk of the account being blocked, and cost).
- For now the chat shows `[template: name]` instead of the real content.
- Template messages sent outside the window may cost money in Meta according to its rates; check them before promoting this.

## Suggestions (your call)
- Make `business_id` required when connecting a WhatsApp account, because templates need it and today it cannot be corrected afterwards. It changes the contract of #8.
