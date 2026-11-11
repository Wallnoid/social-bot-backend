# syntax=docker/dockerfile:1.7
# ==============================================================================
# Stage 1: Base image with dependencies
# ==============================================================================
FROM python:3.12-slim AS base

# Prevents Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
# Prevents Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        git \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# wanps-core lives in a private GitHub repo: the token arrives as a build secret,
# is used only by this step and never ends up in an image layer
COPY pyproject.toml ./
RUN --mount=type=secret,id=github_token,required=true \
    token="$(cat /run/secrets/github_token)" \
    && git config --global url."https://x-access-token:${token}@github.com/".insteadOf "https://github.com/" \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir . \
    && rm -f /root/.gitconfig

# ==============================================================================
# Stage 2: Production image
# ==============================================================================
FROM python:3.12-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from base stage
COPY --from=base /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=base /usr/local/bin /usr/local/bin

# Create non-root user
RUN groupadd -r django && useradd -r -g django django

# Create necessary directories
RUN mkdir -p /app/staticfiles /app/media /app/logs \
    && chown -R django:django /app

# Copy application code
COPY --chown=django:django . .

# Collect static files
RUN python manage.py collectstatic --noinput 2>/dev/null || true

# Switch to non-root user
USER django

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# Run with gunicorn and uvicorn workers: HTTP and the WebSockets of the inbox on the same port
CMD ["gunicorn", "config.asgi:application", \
     "--worker-class", "uvicorn_worker.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
