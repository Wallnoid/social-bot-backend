## Story
As a user of the suite, I want my session to be renewed with a token kept in a cookie that the page cannot read, so that a malicious script cannot steal my long-lived session.

## Acceptance criteria
- [ ] Given I have valid credentials, when I log in, then I receive the access token in the response and the refresh token arrives in an httpOnly cookie that the page's JavaScript cannot read; the refresh token does not appear in the body.
- [ ] Given the refresh cookie, when the app asks for a new access token with the required header, then it receives one and the cookie is replaced by a new one; without the cookie, with an expired or revoked one, or without the header, the API rejects it and hands out no token.
- [ ] Given I am logged in, when I log out, then the refresh token is revoked and the cookie is deleted, so a later refresh fails.

## Plan
- Login and refresh keep the access token in the body and move the refresh token to an httpOnly cookie, with `SameSite=Strict`, limited to the authentication routes and with the same lifetime as the token (7 days). The refresh token no longer comes out in the body.
- Refresh and logout read the token only from the cookie. Refresh still rotates the token and revokes the previous one, and sets the new cookie. Logout revokes it and deletes the cookie.
- Refresh and logout require a custom header in addition to `SameSite`, as a defence against CSRF.
- It builds on what SimpleJWT already does (issue, rotate and revoke), without reimplementing tokens.
- The `Secure` attribute is controlled by an environment variable (off locally, on in production), and it is documented that the frontend and the API must share a base domain.

## Out of scope
- Changing the lifetime of the tokens (60 minutes for access, 7 days for refresh).
- Keeping the access token in a cookie: it stays in memory and travels in the `Authorization` header.
- Clients that are not browsers, such as a mobile app.
- Logging out of all devices at once.
- The frontend changes (repo `social-bot-frontend`).

## Decisions made
- The frontend and the API live on different subdomains of the same base domain (for example `app.example.com` and `api.example.com`), so the cookie is same-site and `SameSite=Strict` works.
- The cookie is called `refresh_token`, is limited to `/api/v1/accounts/`, has no `Domain` attribute (only the API host receives it) and its `Secure` attribute comes from an environment variable.
- Refresh and logout require the header `X-Requested-With`; without it the API answers 403.
- A refresh without a cookie, or with an invalid one, answers 401.
- Logout always deletes the cookie and answers 200, even if the cookie is missing or no longer valid: whoever wants to leave, leaves.
- The refresh token is removed from the body with no transition period: the frontend is the only client, and while the body kept returning it a malicious script could still read it. The two existing tests that read it from the body change.
- The frontend must call with `credentials: "include"`, send the header on refresh and logout, and ask for a new access token when the app loads.
