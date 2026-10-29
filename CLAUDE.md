# Social Bot Backend

## Context
Backend of the Social Bot suite, an omnichannel messaging and CRM platform (similar to Kommo or respond.io). Teams answer WhatsApp Business API, Messenger and Instagram messages from one inbox, and manage contacts, a sales pipeline, appointments and notifications. It is multi-tenant: each tenant (business) has its own channel accounts, bots, users and data. The frontend talks only to this backend.

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
- Planned apps (not created yet): tenants, conversations/inbox, contacts + pipeline (CRM), appointments (calendar), notifications. Details in `docs/architecture.md`.

## Business rules
Summary of the most critical ones (full detail in the imported file below):
- Everything is scoped to a tenant; no query, handler or reply may cross tenants.
- The frontend never calls Meta; every action goes through this backend's API. `wanps.inbox` is installed and served by this backend.
- Initial roles: agent, supervisor, admin.
- Appointments belong to a contact; contacts live in a pipeline.
- Channel secrets are stored encrypted and never returned by the API.

## Conventions
- Code, identifiers, docs and commit messages in English.
- API is versioned under `/api/v1/`; errors use the custom exception handler's JSON format.
- New apps go under `apps/` and follow the layout of `apps/accounts/` (models, serializers, views, urls, admin, tests).
- Emails are stored in lowercase, login ignores capitalization, and the database rejects two users whose emails differ only by case.
- Per-area rules live in `.claude/rules/`.

## Detailed documentation
@docs/architecture.md
@docs/business-rules.md
