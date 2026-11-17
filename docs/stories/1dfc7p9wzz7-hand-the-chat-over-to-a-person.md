## Story
As a client who writes to a business, I want to ask to talk to a person and have the bot stop answering me, so that someone real takes care of me.

ClickUp: 1dfc7p9wzz7

## Acceptance criteria
- [ ] Given a client who asks to talk to a person, or a case the bot cannot solve with its instructions, when they write, then the bot tells them in their language that a person will take care of them and stops answering in that chat; their next messages are saved without calling the AI.
- [ ] Given a chat that waits for a person, when the team looks at the list or the chat, then it sees it marked as "waits for a person" and since when, and hears about it in real time.
- [ ] Given that chat, when a person replies or someone resumes the bot, then the mark goes away and the normal flow follows: if a person replied, the bot stays silent one hour from that reply and then takes over again.

## Plan
- A new internal tool the AI calls to ask for a person. It pauses the bot with no end, saves the mark of the chat with its date, and tells the AI what to say to the client.
- A platform rule that says when to call it, checked against the real model as was done with the rule for messages unrelated to the business.
- The list and the chat show `waiting_for_person_since` (a date or `null`), and an event tells the team when it appears and when it goes away.
- If a person replies, that pause is replaced by the one-hour pause; a pause set by hand stays untouched. Resuming the bot also clears the mark.
- Tests: the request pauses and marks, the next messages do not call the AI, a reply of a person clears the mark and leaves one hour, resuming clears the mark, a pause set by hand does not change, isolation between businesses, and the events.

## Out of scope
- Telling the team by email or phone (the notifications module does not exist yet).
- Assigning the chat to a given person.
- The bot taking over again by itself if nobody answers in some hours.
- Opening hours ("out of hours, we will write to you tomorrow").

## Decisions (agreed)
- The mark lives in a small table, one row per chat while it waits, like the warning of a failure of the AI; not a special value of `paused_by`, which would be ambiguous and shown as a name.
- The bot asks for a person when the client asks for one, or when they have a complaint or a case the instructions of the business do not cover.
- If nobody answers, the chat waits with no limit; a maximum wait could be another story.
- The event is its own, `handover.changed`, with `waiting_for_person_since`, like `failure.changed`.
