# CLAUDE.md

Context for Claude Code working in this repository.

## Purpose

Portfolio project (phase 4, API service): the batch project's daily weather and air-quality
marts (`marts.json` on the `data` branch of antilles-data-pipeline) loaded into PostgreSQL and
served by a read-only FastAPI app behind API keys. The owner is an FPGA / embedded engineer
moving toward freelance data engineering, so code quality, tests and clear docs matter more
than feature count. Every change should be something a recruiter can read.

## Stack

- Python 3.12+ package `src/weather_api` (FastAPI app, loader, key commands, CLI `weather-api`)
- PostgreSQL (Neon in production, Docker Compose on port 5435 locally), SQLAlchemy Core,
  Alembic migrations
- Google Cloud Run (project `antilles-hurricanes`, region `us-east4`), Terraform in `infra/`
- pytest against a real PostgreSQL (HTTP mocked with respx), ruff, mypy --strict

## Commands

```bash
python -m venv .venv && source .venv/bin/activate
make install / db / check
```

## Rules

- Run `make check` before every commit; it must pass (it needs `make db` running).
- Never call GitHub, Google Cloud or Neon from pytest.
- Serve complete days only (`hours_observed = 24`); keep Neon asleep between loads (key
  format check, key cache, in-memory quota and response cache).
- `terraform apply` only after the owner approves the plan; no secrets in the repository.
- Keep mypy strict; no `type: ignore` without a comment explaining why.
- Code, comments, commits and README in English.
- Small commits with clear messages; open a PR per feature so CI runs.
