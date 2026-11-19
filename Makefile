.PHONY: install db lint typecheck test check migrate load run clean

install:
	pip install -c requirements.lock -e ".[dev]"

# Local PostgreSQL on port 5435 (5433 and 5434 belong to the other projects).
db:
	docker compose up -d db

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy

test:
	pytest

check: lint typecheck test

migrate:
	alembic upgrade head

load:
	weather-api load

run:
	uvicorn weather_api.app:app --reload --port 8000

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage
