# CRM for the frontend

> What the frontend can build on today. The exact request and response schemas are in the API docs (`/api/docs/`, `/api/redoc/`); this page is the map.

## Trying it with demo data
- Start the services (`make docker-up`) and, in development, seed the demo data:
  `docker compose run --rm web python manage.py seed_demo --reset` (needs `SEED_DEMO_PASSWORD` in `.env`; the password is never printed).
- Log in at `POST /api/v1/accounts/token/` with one of the demo users (the password is the value of `SEED_DEMO_PASSWORD`):
  - `demo-admin@demo.test`, `demo-supervisor@demo.test`, `demo-agent@demo.test`: roles of the business `demo-Acme Dental`.
  - `demo-multi@demo.test`: admin of Acme and agent of `demo-Rival Clinic` (to try the business switch).
  - `demo-rival-admin@demo.test`: admin of the other business (to check that data never crosses).
- Acme has about 180 contacts spread over the five stages, with data, tags, notes, people in charge and one contact that is two chats merged (WhatsApp + Messenger).

## Rules for every call
- Header `Authorization: Bearer <access token>` and header `X-Tenant-ID: <business id>`: everything is scoped to the active business.
- Answers are `{"success": true, "data": ...}`; errors use the project's error format (`errors` has the fields).
- Any member (agent, supervisor, admin) can use the contact, note, tag and merge endpoints. Managing the stages is for admins.
- Lists are paged with `limit` and `offset`, and answer `has_more`.

## Contacts (`/api/v1/crm/`)
| Call | What it is for |
|---|---|
| `GET contacts/` | The list. Filters, all optional and combinable: `stage` (id), `search` (part of the name or phone), `tag` (repeat it for several: the contact needs all), `assigned_to` (member id, or `none`). An unknown stage, tag or member answers 400. Most recent contact first. |
| `GET contacts/<id>/` | The file: the list fields plus `account`, `first_contact_at` and `conversations` (every chat of the contact, its own first, each with its last message). |
| `PATCH contacts/<id>/` | Edit `name`, `phone`, `email`, `company`, `stage` and `assigned_to` (member id, or empty to take the person off). |
| `POST contacts/<id>/merge/` | Merge another contact into this one: body `{"contact": "<id of the one that goes>"}`. It cannot be undone. Answers the file of the contact that stays. |

Things to know when drawing a contact:
- `name` is what to show; `custom_name` is what the team wrote (fill edit forms from it). On WhatsApp `name` can be empty: show `contact_id`, the phone.
- `assigned_to` is `{id, name}` or `null`; `id` is the id of the member, the one the member list gives.
- A merged contact has several `conversations`; open each one in the inbox of its channel.

## Pipeline (stages)
| Call | What it is for |
|---|---|
| `GET stages/` | The columns in order, each with how many contacts it has. |
| `GET contacts/?stage=<id>` | The cards of a column (paged). |
| `PATCH contacts/<id>/` with `stage` | Move a card to another column. |
| `POST stages/`, `PATCH stages/<id>/`, `DELETE stages/<id>/`, `PUT stages/order/` | Create, rename, delete and reorder columns (admins). Deleting a stage with contacts needs `move_to`. |

## Notes and tags
| Call | What it is for |
|---|---|
| `GET` / `POST contacts/<id>/notes/` | List (paged) and add internal notes. |
| `PATCH` / `DELETE contacts/<id>/notes/<note_id>/` | Edit (only the author) and delete (the author or an admin). |
| `POST contacts/<id>/tags/` | Tag a contact by name (a new name creates the tag). Answers 201 if the contact did not have it, 200 if it did. |
| `DELETE contacts/<id>/tags/<tag_id>/` | Take a tag off a contact. |
| `GET tags/` | The tags of the business, each with how many contacts have it. |

## From the inbox
- The messages of a chat (`GET /api/v1/inbox/<channel>/conversations/<contact_id>/messages/`) bring `contact`: its `id` and its stage, so the inbox can open the file and move the stage. A chat merged into another contact brings the contact that stays.

## Known limits
- Merging cannot be undone, and the name shown for a merged contact is the one of the contact that stays.
- The stage and tag lists are not paged.
