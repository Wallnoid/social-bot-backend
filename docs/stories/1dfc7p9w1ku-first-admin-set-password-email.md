## Story
As the first admin of a business, I want to receive an email with a link to create my password, so that I can sign in to the suite for the first time.

## Acceptance criteria
- [ ] Given the Social Bot team creates a business with a first admin who has no password, when the business is saved, then that person receives an email with a link to create their password.
- [ ] Given I have a valid link, when I create my password with it, then I can log in with my email and that password, and the link stops working.
- [ ] Given the link was already used or expired, when I try to create the password with it, then the API rejects it with a clear message.

## Plan
- When creating the business, if the first admin has no usable password, send them an email with a link to the frontend carrying a single-use token that expires after 7 days. If they already have a password, nothing is sent.
- A public API endpoint that receives the token and the new password, validates it with Django's password rules and saves it.
- The frontend URL goes in an environment variable (`FRONTEND_URL`); until it exists, a placeholder value stays in `.env`.
- Sending uses the existing email configuration: console locally and SMTP in production, with Hostinger's `contact@wanps.tech` mailbox.
- Tests: email sent with the link, password created and successful login, used or expired link rejected, and no email if the user already has a password.

## Out of scope
- Resending the email if it expires or is lost.
- The frontend screen that receives the link (it is another project).
- The email design (plain text for now).
- "Forgot my password" for users who already have one.
- Accepting invitations (#5), although it will reuse this mechanism.

## Suggestions (your call)
- Django already has a single-use token generator for password resets, which stops being valid as soon as the password changes. Using it avoids creating a model and migration for the token, and #5 can reuse it.
- The SMTP details of the Hostinger mailbox (server, port and encryption) must be taken from its panel. The current production configuration uses STARTTLS on port 587 with Gmail by default; if Hostinger requires SSL on 465, that option will have to be added. The mailbox password goes only in environment variables.
