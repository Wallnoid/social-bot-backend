## Story
As a business admin, I want to set up the Meta App of my business from the frontend (name, app id, app secret, verify token), so that I can connect WhatsApp, Messenger and Instagram without going through the Django admin.

## Acceptance criteria
- [ ] Given I am an admin of my business, when I send the data of my Meta App (name, app id, app secret, verify token and, optionally, the API version), then it is saved and assigned to my business, and I get back the webhook URL to paste in Meta. The app secret and the verify token never come back in any response. If I am an agent or a supervisor, I get 403.
- [ ] Given my business already has its Meta App, when I read it, edit it or deactivate it, then I see its data without the secret, the changes apply, and connecting accounts uses the app right away (or answers that it is not set up if I deactivated it).
- [ ] Given my business has its Meta App set up, when I connect a WhatsApp, Messenger or Instagram account with `POST /api/v1/channels/accounts/`, then it is connected to that app and never to the app of another business.

## Plan
- One endpoint, `/api/v1/channels/meta-app/`, for the app of my business (create, read, edit), admin only, with the rule the accounts already follow: the secret goes in and never comes out.
- Each business has at most one app of its own. A business with its own app uses only that one, as the current rule says.
- The response includes the webhook URL built from the key of the app, so the frontend can show what to paste in Meta.
- Tests by role, checking that the secret is never returned and that a business never sees or touches the app of another.

## Out of scope
- The shared Meta App of Social Bot: the team keeps marking it in the Django admin, which stays as it is (Social Bot staff can still set up any Meta App there).
- Connecting with Facebook Login or Embedded Signup.
- Creating the app or its webhook in Meta's panel.

## Decisions made
- The `app_secret` and the `verify_token` are write-only, like every channel secret (rule 8 of the business rules). The admin chose the verify token, so they know it; if they forget it, they send a new one and paste it again in Meta.
- A Meta App that is the shared app of Social Bot, or that the team assigned to other businesses, is not the business's own: reading it shows only its name and state (`shared: true`), and editing it answers 403.
- Two Meta Apps cannot have the same app id; the answer does not say who has it.
- A business with its own app uses only that one. If the admin deactivates it, the business cannot connect accounts until it is active again, as today.
- The app cannot be deleted from the API, only deactivated.
- The Django admin keeps working for the same data; this story adds the API, it does not remove the admin.
