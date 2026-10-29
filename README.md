# Social Bot Backend

Backend for the Social Bot suite: reply to WhatsApp Business API, Messenger and Instagram messages, plus calendar, CRM and notifications. Channels are provided by `wanps-core`.

## 🎯 What it is

An omnichannel messaging and CRM suite (similar to Kommo or respond.io):

- **Inbox:** answer WhatsApp Business API, Messenger and Instagram messages from one place, with a pausable bot per conversation.
- **CRM:** contacts and a sales pipeline.
- **Calendar:** appointments linked to contacts.
- **Notifications.**
- **Multi-tenant:** each business has its own channel accounts, bots, users and data.
- **Roles (initial):** agent, supervisor, admin.

The frontend talks only to this backend. Channel connections come from [`wanps-core`](../wanps-core) (sibling repo); see its README for webhooks, multi-tenant mode and the AI handlers. The CRM, calendar, notifications and inbox modules are planned and not built yet; today the repo has the base (users, JWT auth, Docker, Celery). More detail in `CLAUDE.md` and `docs/`.

## ✨ Features

| Feature | Description |
|---|---|
| **Django 5.2+** | Latest Django with async support |
| **Django REST Framework** | Full-featured REST API with serializers, viewsets, and permissions |
| **JWT Authentication** | Access & refresh tokens via `djangorestframework-simplejwt` |
| **Custom User Model** | Email-based auth, UUID PKs, profile fields |
| **PostgreSQL** | Production-grade database (dockerized) |
| **Redis** | Caching and Celery broker |
| **Celery + Beat** | Background tasks and periodic jobs |
| **API Documentation** | Auto-generated Swagger UI & ReDoc via `drf-spectacular` |
| **CORS Headers** | Cross-origin support for SPA frontends |
| **Soft Delete** | Logical deletion with restore capability |
| **Rate Limiting** | Throttling per user and per IP |
| **Filtering & Search** | Full queryset filtering with `django-filter` |
| **API Versioning** | URL-based API versioning (`/api/v1/`) |
| **Health Checks** | Endpoints for monitoring and load balancers |
| **Custom Exception Handler** | Consistent JSON error format |
| **Request Logging** | Middleware that logs every request with timing |
| **Split Settings** | Separate configs for local and production |
| **Docker** | Multi-stage Dockerfile + docker-compose |
| **Testing** | pytest + factory-boy + full test suite |
| **Code Quality** | Ruff linter + mypy type checking |

## 📁 Project Structure

```
├── config/                    # Project configuration
│   ├── settings/
│   │   ├── base.py            # Shared settings
│   │   ├── local.py           # Development settings
│   │   └── production.py      # Production settings
│   ├── urls.py                # Root URL configuration
│   ├── celery.py              # Celery configuration
│   ├── wsgi.py                # WSGI entry point
│   └── asgi.py                # ASGI entry point
│
├── apps/                      # Django applications
│   ├── accounts/              # User authentication & management
│   │   ├── models.py          # Custom User model
│   │   ├── serializers.py     # API serializers
│   │   ├── views.py           # API views
│   │   ├── urls.py            # URL routing
│   │   ├── admin.py           # Admin configuration
│   │   ├── signals.py         # Post-save signals
│   │   └── tests/             # Test suite
│   │
│   └── core/                  # Shared utilities
│       ├── models.py          # BaseModel (UUID, timestamps, soft delete)
│       ├── pagination.py      # Pagination classes
│       ├── permissions.py     # Shared permissions
│       ├── exceptions.py      # Custom exception handler
│       ├── throttling.py      # Rate limiting
│       ├── middleware.py      # Request logging
│       └── utils.py           # Helper functions
│
├── docker-compose.yml         # PostgreSQL + Redis + Django + Celery
├── Dockerfile                 # Multi-stage production build
├── Makefile                   # Common commands
├── pyproject.toml             # Dependencies & tool config
└── .env.example               # Environment variables example
```

## 🐳 Docker Architecture & Services

When you run this project using Docker (`docker-compose.yml`), it spins up the following interconnected services:

1. **`db` (PostgreSQL 16):** The primary relational database.
   - **Configuration File:** `docker-compose.yml` (lines 14-26)
   - **Django Settings:** `config/settings/base.py` (lines 104-109) & `config/settings/local.py` (lines 19-24)
2. **`redis` (Redis 7):** Used as both the in-memory cache backend for Django and the message broker for Celery.
   - **Configuration File:** `docker-compose.yml` (lines 28-38)
   - **Django Cache Settings:** `config/settings/base.py` (lines 212-220)
3. **`web` (Django Gunicorn):** The main REST API application server.
   - **Configuration File:** `docker-compose.yml` (lines 40-59)
   - **Dockerfile:** `Dockerfile` (multi-stage build)
4. **`celery-worker`:** Executes asynchronous background tasks (e.g., sending emails) offloaded from the main API.
   - **Configuration File:** `docker-compose.yml` (lines 61-76)
   - **Celery Setup:** `config/celery.py` (lines 1-28) & `config/settings/base.py` (lines 201-208)
5. **`celery-beat`:** The scheduler for periodic cron-like tasks (e.g., daily reports).
   - **Configuration File:** `docker-compose.yml` (lines 78-93)

## 🚀 Quick Start

### 1. Clone and configure

```bash
git clone <repository-url>
cd social-bot-backend

# Copy environment variables
cp .env.example .env
```

### 2. Start with Docker (recommended)

```bash
# Start all services (PostgreSQL, Redis, Django, Celery)
docker compose up -d --build

# Run migrations
docker compose exec web python manage.py migrate

# Create admin user
docker compose exec web python manage.py createsuperuser

# View logs
docker compose logs -f web
```

### 3. Or start locally

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -e ".[dev]"

# Start PostgreSQL and Redis via Docker
docker compose up -d db redis

# Run migrations
python manage.py migrate

# Create admin user
python manage.py createsuperuser

# Start development server
python manage.py runserver
```

## 📡 API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/accounts/token/` | Obtain JWT token pair |
| POST | `/api/v1/accounts/token/refresh/` | Refresh access token |
| POST | `/api/v1/accounts/token/verify/` | Verify token |
| POST | `/api/v1/accounts/token/blacklist/` | Logout (blacklist token) |

### Users
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/accounts/users/` | List users (admin) |
| GET | `/api/v1/accounts/users/me/` | Current user profile |
| PUT/PATCH | `/api/v1/accounts/users/me/` | Update profile |
| POST | `/api/v1/accounts/users/me/change-password/` | Change password |

### Documentation & Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/docs/` | Swagger UI |
| GET | `/api/redoc/` | ReDoc |
| GET | `/api/schema/` | OpenAPI schema |
| GET | `/health/` | Health check |
| GET | `/admin/` | Django admin panel |

## 🧪 Testing

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
pytest apps/accounts/tests/test_models.py

# Run with Docker
make docker-test
```

## 🛠 Useful Commands

```bash
make help            # Show all available commands
make install         # Install dependencies
make run             # Start dev server
make migrate         # Run migrations
make test            # Run tests
make lint            # Run linter
make format          # Format code
make docker-up       # Start Docker services
make docker-down     # Stop Docker services
make docker-logs     # Follow logs
```

## 🏗 Adding a New App

1. Create the app directory:
```bash
mkdir -p apps/your_app
```

2. Create the app files following the same pattern as `apps/accounts/`.

3. Add `"apps.your_app"` to `LOCAL_APPS` in `config/settings/base.py`.

4. Create and run migrations:
```bash
python manage.py makemigrations your_app
python manage.py migrate
```

5. Include the URLs in `config/urls.py`:
```python
path("api/v1/", include([
    path("accounts/", include("apps.accounts.urls")),
    path("your-app/", include("apps.your_app.urls")),  # Add this
])),
```

## 📝 Environment Variables

See [`.env.example`](.env.example) for all available environment variables.

## 📄 License

MIT License
