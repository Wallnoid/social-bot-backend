# Social Bot Backend

## Context
Backend of the Social Bot suite, an omnichannel messaging and CRM platform (similar to Kommo or respond.io). Teams answer WhatsApp Business API, Messenger and Instagram messages from one app, with a separate inbox per channel, and manage contacts, a sales pipeline, appointments and notifications. It is multi-tenant: each tenant (business) has its own channel accounts, bots, users and data. The frontend talks only to this backend.

Channel connections (webhooks, sending, conversations, AI handlers) come from `wanps-core`, a sibling repo at `../wanps-core` (see its `README.md`). This repo consumes it and does not reimplement it.

## Stack
- Language / framework: Python >= 3.12, Django 5.2, Django REST Framework, SimpleJWT
- Database: PostgreSQL 16 (UUID primary keys, soft delete in `BaseModel`)
- Async / cache: Redis 7, Celery + Celery Beat
- API docs: drf-spectacular (`/api/docs/`, `/api/redoc/`)
- Infra / deployment: Docker (multi-stage `Dockerfile`, `docker-compose.yml` with db, redis, web, celery-worker, celery-beat)

## Commands
- Install dependencies: `make install` (`pip install -e ".[dev]"`)
- Run in development: `make run` (or `make docker-up`)
- Migrations: `make makemigrations` / `make migrate`
- Tests: `make test` (`make test-cov` for coverage, `make docker-test` in Docker)
- Lint / format: `make lint` / `make format` (ruff), `make typecheck` (mypy)
- Build: `make docker-build`

## Project structure
- `config/`: settings (`base.py`, `local.py`, `production.py`), root URLs, Celery, WSGI/ASGI
- `apps/core/`: shared base model (UUID, timestamps, soft delete), pagination, permissions, throttling, exception handler, request logging, health checks
- `apps/accounts/`: custom email-based `User`, JWT auth endpoints
- `apps/tenants/`: businesses, memberships, roles, invitations
- `apps/channels/`: channel accounts of each business (a link to the `wanps-core` account) and the Meta Apps they connect to
- `apps/conversations/`: the inbox, one per channel, read through `wanps.inbox`
- `apps/devtools/`: development only (listed in the local settings, never in production): the `seed_demo` command and the fake Meta (`META_FAKE=true`)
- Planned apps (not created yet): contacts + pipeline (CRM), appointments (calendar), notifications. Details in `docs/architecture.md`.

## Business rules
Summary of the most critical ones (full detail in the imported file below):
- Everything is scoped to a tenant; no query, handler or reply may cross tenants.
- The frontend never calls Meta; every action goes through this backend's API. `wanps.inbox` is installed and its logic is served by this backend.
- The inbox is one per channel under `/api/v1/inbox/<channel>/`; it reads through `wanps.inbox.services` with a `TenantInbox` limited to the active business's connected accounts, and `wanps.inbox`'s own keyed API is never mounted.
- On Messenger and Instagram, a person can reply 24 hours to 7 days after the client's last message by sending `human_agent: true` in the send action; it is rejected on WhatsApp.
- Initial roles: agent, supervisor, admin.
- Appointments belong to a contact; contacts live in a pipeline.
- Channel secrets are stored encrypted and never returned by the API.

## Conventions
- Code, identifiers, docs and commit messages in English.
- API is versioned under `/api/v1/`; errors use the custom exception handler's JSON format.
- New apps go under `apps/` and follow the layout of `apps/accounts/` (models, serializers, views, urls, admin, tests).
- Emails are stored in lowercase, login ignores capitalization, and the database rejects two users whose emails differ only by case.
- Password links use Django's token generator; their lifetime comes from `PASSWORD_RESET_TIMEOUT` in `.env` and emails link to `FRONTEND_URL`. Outgoing email uses the SMTP settings from `.env`; local defaults to the console.
- The active business comes from the `X-Tenant-ID` header; views opt in with `HasActiveTenant` (`apps/tenants/permissions.py`), which sets `request.tenant` and `request.membership`.
- Invitation expiry comes from `INVITATION_TIMEOUT` in `.env`; a view that needs an admin of the active business adds `IsTenantAdmin` after `HasActiveTenant`.
- The refresh token travels only in the httpOnly cookie `refresh_token` (`SameSite=Strict`, path `/api/v1/accounts/`, `Secure` from `AUTH_REFRESH_COOKIE_SECURE`), never in a body; refresh and logout require the `X-Requested-With` header, and the access token goes in the `Authorization` header.
- Per-area rules live in `.claude/rules/`.

## Detailed documentation
@docs/architecture.md
@docs/business-rules.md
