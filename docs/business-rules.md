# Business rules

> Status: rules agreed so far. Values and limits not listed here have not been decided; ask before assuming.

## Glossary
| Term | Meaning |
|---|---|
| Tenant | A business using the suite, with its own users, channel accounts, contacts and data |
| Channel | WhatsApp Business API, Messenger or Instagram |
| Channel account | One connected number or page of a tenant on a channel (a `wanps-core` account) |
| Conversation | The chat between a contact and a tenant on a channel account; the bot can be paused per conversation |
| Contact | A client of the tenant, identified by its channel ids and profile data |
| Pipeline | Ordered stages a contact moves through (CRM) |
| Appointment | A calendar entry linked to a contact |
| Bot / handler | Automatic replies for an account (fixed logic or an LLM agent from `wanps.ai`) |
| Agent / supervisor / admin | Initial user roles |

## Rules
1. **Tenant isolation:** every record belongs to a tenant. Data, handlers, replies, notifications and API responses are always scoped to the requesting user's tenant.
2. **Single entry point:** the frontend only uses this backend's API. It never receives channel tokens, app secrets or `wanps-core` keys.
3. **Roles (initial):**
   - *agent*: answers conversations and works contacts and appointments.
   - *supervisor*: everything an agent does, plus oversight of the team's conversations and pipeline.
   - *admin*: everything a supervisor does, plus managing users, channel accounts and tenant settings.
   Exact permissions per endpoint are decided when each feature is built.
4. **Contacts and pipeline:** contacts (clients) are organized in a pipeline. Stages and transition rules are not defined yet.
5. **Appointments:** an appointment always belongs to a contact.
6. **Bot and people:** a person can pause the bot in a conversation; while paused the bot does not reply.
7. **Idempotent messages:** an incoming message is processed once, even if Meta resends the webhook (dedup by external id, handled by `wanps-core`).
8. **Secrets:** channel tokens and keys are stored encrypted (`WANPS_ENCRYPTION_KEY`) and never returned by the API.
9. **Soft delete:** models based on `BaseModel` are deleted logically and can be restored.

## Special cases
- WhatsApp Business API numbers cannot be used from the WhatsApp Business app, so every human reply must go through this system.
- One contact can write from several channels; whether those become one contact or several is **undecided**.
- Losing `WANPS_ENCRYPTION_KEY` makes stored tokens unreadable; they must be entered again.

## Things that must NOT be done
- Do not query or return data without filtering by tenant.
- Do not let the frontend call Meta or hold channel tokens; it only uses this backend's API (including the `wanps.inbox` endpoints it serves).
- Do not log or print tokens, secrets or the `.env` contents.
- Do not reimplement in this repo what `wanps-core` already provides (webhooks, sending, dedup, bot dispatch); extend or fix it there.
- Do not put client-specific logic in `wanps-core`.
