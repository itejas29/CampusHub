# Convenience wrappers around the Docker Compose stack.
COMPOSE ?= docker compose

.PHONY: help up down logs restart build seed reset-db migrate revision shell-api shell-db test clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: ## Build and start the full stack
	$(COMPOSE) up --build

down: ## Stop the stack (keeps data)
	$(COMPOSE) down

clean: ## Stop the stack and delete volumes (destroys the database)
	$(COMPOSE) down -v

logs: ## Tail all logs
	$(COMPOSE) logs -f

restart: ## Restart the API
	$(COMPOSE) restart backend

migrate: ## Apply database migrations
	$(COMPOSE) exec backend alembic upgrade head

revision: ## Autogenerate a migration: make revision m="add x"
	$(COMPOSE) exec backend alembic revision --autogenerate -m "$(m)"

seed: ## Load demo data (skips if data already exists)
	$(COMPOSE) exec backend python -m app.seed.run

reset-db: ## Rebuild the schema and reload demo data
	$(COMPOSE) exec backend python -m app.seed.run --reset

shell-api: ## Shell inside the API container
	$(COMPOSE) exec backend bash

shell-db: ## psql inside the database container
	$(COMPOSE) exec postgres psql -U campushub -d campushub

test: ## Run the backend test suite
	$(COMPOSE) exec backend pytest -q
