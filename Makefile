.PHONY: up down build migrate shell test lint format check

up:            ## Start Django and PostgreSQL in Docker
	docker compose up --build

down:          ## Stop the Docker stack
	docker compose down

migrate:       ## Apply database migrations
	docker compose run --rm web python manage.py migrate

shell:         ## Open a Django shell
	docker compose run --rm web python manage.py shell

test:          ## Run the test suite (needs PostgreSQL on localhost:5432, e.g. `docker compose up db`)
	uv run pytest

lint:          ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

format:        ## Auto-fix lint issues and format code
	uv run ruff check --fix .
	uv run ruff format .

check: lint    ## Everything CI runs
	uv run python manage.py makemigrations --check --dry-run --settings=config.settings.test
	uv run pytest
