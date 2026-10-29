# ==============================================================================
# Django Backend Template — Makefile
# ==============================================================================
# Quick reference for common commands.
# Usage: make <target>
# ==============================================================================

.PHONY: help install run migrate makemigrations superuser test lint format \
        docker-up docker-down docker-build docker-logs shell dbshell \
        collectstatic check clean

# Default target
help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ==============================================================================
# Local Development
# ==============================================================================

install: ## Install dependencies (pip install with dev extras)
	pip install -e ".[dev]"

run: ## Run the development server
	python manage.py runserver 0.0.0.0:8000

migrate: ## Run database migrations
	python manage.py migrate

makemigrations: ## Create new migrations
	python manage.py makemigrations

superuser: ## Create a superuser
	python manage.py createsuperuser

shell: ## Open Django shell (IPython)
	python manage.py shell

dbshell: ## Open database shell
	python manage.py dbshell

collectstatic: ## Collect static files
	python manage.py collectstatic --noinput

check: ## Run Django system checks
	python manage.py check
	python manage.py check --deploy 2>&1 || true

# ==============================================================================
# Testing & Code Quality
# ==============================================================================

test: ## Run tests with pytest
	pytest

test-cov: ## Run tests with coverage report
	pytest --cov=apps --cov-report=term-missing --cov-report=html

lint: ## Run linter (ruff)
	ruff check .

format: ## Format code (ruff)
	ruff format .
	ruff check --fix .

typecheck: ## Run type checker (mypy)
	mypy apps/

# ==============================================================================
# Docker
# ==============================================================================

docker-up: ## Start all Docker services
	docker compose up -d

docker-down: ## Stop all Docker services
	docker compose down

docker-build: ## Build and start Docker services
	docker compose up -d --build

docker-logs: ## Follow Docker logs
	docker compose logs -f

docker-web-logs: ## Follow web service logs
	docker compose logs -f web

docker-migrate: ## Run migrations inside Docker
	docker compose exec web python manage.py migrate

docker-superuser: ## Create superuser inside Docker
	docker compose exec web python manage.py createsuperuser

docker-shell: ## Open shell inside Docker web container
	docker compose exec web python manage.py shell

docker-test: ## Run tests inside Docker
	docker compose exec web pytest

# ==============================================================================
# Database (Docker)
# ==============================================================================

db-up: ## Start only the database service
	docker compose up -d db

db-reset: ## Reset database (WARNING: destroys all data)
	docker compose down -v
	docker compose up -d db
	@echo "Waiting for database..."
	@sleep 3
	python manage.py migrate

# ==============================================================================
# Cleanup
# ==============================================================================

clean: ## Remove Python cache files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage
