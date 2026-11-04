## Story
As a business admin, I want to connect my business's own WhatsApp number, Messenger page or Instagram account, so that my messages arrive in my business.

## Acceptance criteria
- [ ] Given I am an admin of the active business and it has its own active Meta App, when I connect an account with its channel, name, id and access token, then it is created on my business's Meta App and belongs to my business.
- [ ] Given my business has no Meta App of its own, when I connect an account, then it is created on the shared Social Bot Meta App.
- [ ] Given my business has its own Meta App but it is inactive, or it has none and there is no active shared one, when I connect an account, then the API rejects it with a clear message and nothing is created.
- [ ] Given I connected an account, when I read the response, then it never contains the access token, and the token is stored encrypted.
- [ ] Given I connected an account, when a message arrives for it, then it is stored but the bot does not reply (the account starts inactive).
- [ ] Given the account is already connected (to my business or another), when I connect it again, then the API rejects it without saying which business has it.
- [ ] Given I am an agent or supervisor, when I try to connect an account, then the API rejects it.

## Plan
- Install `wanps-core[multitenant] @ git+https://github.com/Wanp-s/wanps-core.git@v0.4.0` (private repo, pinned to the release tag); locally it can be installed editable from `../wanps-core`. Enable `wanps.messaging`, `wanps.whatsapp`, `wanps.messenger`, `wanps.instagram` with `WANPS_MULTITENANT=True`, and mount the Meta webhook at `/webhooks/meta/`.
- `wanps-core` already provides Meta Apps, accounts, webhook, messages, sending and the bot; Social Bot only adds who owns what:
  - an optional `meta_app` on the business: its own Meta App.
  - a single record in Social Bot that marks which Meta App is the shared one.
  - a link from each `wanps-core` account to the business that owns it.
- Choosing the Meta App: a business with its own app uses only that one (an error while it is inactive); a business without one uses the active shared app; otherwise an error.
- An endpoint to connect an account (`whatsapp`, `messenger` or `instagram`), for admins of the active business only.
- The Social Bot team sets a business's own Meta App and the shared one in the Django admin.

## Out of scope
- Embedded Signup (connecting through Meta's login instead of typing the data).
- Checking the token with Meta when connecting.
- Listing, editing or disconnecting accounts (#9).
- Seeing only my business's conversations (#10).
- Configuring or turning on the bot.
- Moving a business's accounts from its own Meta App to the shared one.

## Decisions made
- Both setups are supported: one shared Meta App for every business, or a business with its own Meta App (needed while Social Bot is not a verified Tech Provider). Which one applies depends only on what is stored in the database.
- The link between Meta Apps, accounts and businesses lives in Social Bot, not in `wanps-core`, because it is client-specific logic.
- Meta App secrets are entered only by the Social Bot team in the Django admin; business admins only enter the account's data and token.
- A connected account starts inactive: messages are stored, the bot does not reply.
- A business with its own Meta App never falls back to the shared one, even while its app is inactive: Meta sends that business's events to its own app, so an account on the shared app would never receive them.
- Only the per-app webhook route (`/webhooks/meta/<webhook_key>/`) is served: the route without a key has no app secret to check signatures against.
- `wanps-core` is private: Docker builds receive a GitHub token as a build secret, never stored in the image or the repo.
