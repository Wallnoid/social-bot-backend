# Architecture

> Status: the repo currently holds the base template (`core`, `accounts`). Everything marked **planned** does not exist yet; it records the agreed direction, not implemented code.

## Overview
```
Frontend (inbox, calendar, CRM)
        │  REST + JWT  (/api/v1/)
        ▼
social-bot-backend (Django + DRF) ──── PostgreSQL
        │      │                        Redis / Celery (async + periodic jobs)
        │      └── wanps-core (installed package)
        ▼              │
   Celery worker       ▼
                 Meta Graph API  ⇄  WhatsApp Business API, Messenger, Instagram
```
- The frontend only talks to this backend. It never calls Meta directly. The inbox endpoints (list chats, read messages, reply, pause bot) come from `wanps.inbox`, installed and mounted in this project, so they are served by this backend.
- Meta sends events to the `wanps-core` webhook (`/webhooks/meta/<key>/`), mounted in this project's URLs. Messages are stored in this project's database.
- `wanps-core` has no database of its own: its tables are created by `migrate` here.
- Sending, bot pausing and conversation history go through `wanps-core` (`wanps.messaging`, `wanps.inbox`), served under this backend's API.

## Modules
| Module | Responsibility | Status |
|---|---|---|
| `config` | Settings, URLs, Celery | exists |
| `apps.core` | Base model, pagination, permissions, throttling, errors, logging, health | exists |
| `apps.accounts` | Users, JWT auth | exists |
| tenants | Tenant (business), membership, roles, link to `wanps-core` accounts | planned |
| conversations (inbox) | List chats, read messages, reply as a person, pause/resume bot; built on `wanps.inbox` | planned |
| contacts + pipeline (CRM) | Contacts (clients), pipeline stages, link to conversations | planned |
| appointments (calendar) | Appointments linked to contacts | planned |
| notifications | Notify users of new messages, appointments and pipeline changes | planned |

App names are provisional; decide them when each one is built.

## Key flows
- **Incoming message (planned wiring):** Meta → `wanps-core` webhook → signature check and dedup → message stored → dispatcher runs the account's handler (Celery) → handler may reply or leave the chat to a person → notification to the tenant's users.
- **Reply as a person (planned):** frontend → this backend (`wanps.inbox` API) → permission and tenant check → `wanps.messaging.send` → Meta.
- **Auth:** email + password → JWT access/refresh pair (`/api/v1/accounts/token/`); logout blacklists the refresh token.

## External integrations
- `wanps-core` (sibling repo `../wanps-core`): channels, messaging tables, AI handlers. Not yet a dependency in `pyproject.toml`; installing it (editable or from GitHub) and the settings it needs (`WANPS_MULTITENANT`, `WANPS_ENCRYPTION_KEY`, Meta App settings) are part of the first story that needs it.
- Meta: WhatsApp Business API (Cloud), Messenger, Instagram DMs, through `wanps-core`.
- LLM providers (OpenAI, Anthropic, Gemini) through `wanps.ai`, configured per account.

## Technical decisions
- **Multi-tenant via `wanps-core`'s multi-tenant mode:** many channel accounts in one deployment, each with its own credentials and bot.
- **Single entry point:** one API for the frontend keeps auth, roles and tenant isolation in one place. `wanps.inbox` is installed (decided) and served by this backend, not by a separate inbox app.
- **Template base kept:** split settings, UUID PKs, soft delete, JWT and Celery come from the original template and are not being redesigned.

## Open decisions
- Tenant isolation strategy (shared tables with a tenant foreign key vs. other).
- Permission model beyond the three initial roles.
- How `wanps.inbox` keys and this backend's JWT roles/tenants fit together (inbox keys are per account and bypass user login).

## Not needed (decided)
- Offline/sync, multi-language and multi-currency: not required for now.
