# Antilles Weather API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A public, key-protected, read-only REST API over the batch project's daily weather and air-quality marts, loaded daily into Neon PostgreSQL and served by FastAPI on Cloud Run.

**Architecture:** `weather-api load` copies `marts.json` into PostgreSQL (idempotent upsert, one transaction). A FastAPI app serves `/v1` routes over complete days only, with API keys (hashed), an in-memory per-key quota and an in-memory response cache so Neon sleeps between loads. GitHub Actions tests, migrates, builds and deploys to Cloud Run with Workload Identity Federation; Terraform describes the GCP side.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + psycopg 3, Alembic, uvicorn, httpx, pytest + respx, ruff, mypy --strict; Docker; Google Cloud Run, Artifact Registry, Secret Manager, Terraform; Neon PostgreSQL.

**Spec:** `docs/superpowers/specs/2026-11-20-weather-api-design.md`

## Global Constraints

- Package `weather_api` (src layout), CLI `weather-api` (`load`, `keys create|revoke|list`).
- Source: `https://raw.githubusercontent.com/tomtessondev/antilles-data-pipeline/data/marts.json`; fields as in `antilles-data-pipeline/dashboard/src/lib/schema.ts`.
- Complete day = `hours_observed = 24` (per table); "latest" = latest complete day loaded, never today.
- Routes under `/v1`, header `X-API-Key`, keys `aw_` + 43 url-safe characters, SHA-256 stored; demo key 60 requests a minute.
- Errors `application/problem+json` (RFC 9457): 401 key missing/unknown/revoked/malformed, 404 unknown town, 422 invalid parameters, 429 over quota with `Retry-After`; headers `RateLimit-Limit`, `RateLimit-Remaining`; `Cache-Control: public, max-age=300` on data responses.
- Pagination: order (`observed_date`, `location_code`), `limit` default 100 max 500, opaque `cursor`.
- EU PM10 daily limit 50 µg/m³; summary `days` ∈ {7, 14, 30}.
- Database touched only by loads, cache misses and `keys` commands: malformed keys rejected without a query, key hashes cached 60 s, quota counted in memory per instance, data responses cached until `generated_at` changes (checked at most once a minute).
- Local PostgreSQL on host port **5435** (5433/5434 are taken); tests run against a real PostgreSQL, never call GitHub, Google Cloud or Neon.
- GCP project `antilles-hurricanes`, region `us-east4`; own WIF provider in pool `github`, Terraform state `gs://antilles-hurricanes-tfstate` prefix `weather-api`; Cloud Run min 0, max 2 instances, 1 vCPU, 512 MiB. `terraform apply` only after the owner approves the plan.
- `make check` (ruff, ruff format --check, mypy, pytest) before every commit; English code and docs.

## Review Focus

1. A garbled or tampered `cursor` → 422 problem, never 500.
2. A `location` filter naming an unknown town → 404 problem (not an empty page that looks like "no data").
3. Database unreachable (Neon waking or down) → `/health` 503 and `/v1` 503 problem, no stack trace.
4. A revoked key stays usable at most 60 s (cache), then 401.
5. Empty database (before the first load) → `/v1/meta` and data routes answer 503 "no data loaded yet", not 500.

Tests: 1, 2 → Task 6; 3, 4, 5 → Task 5.

---

### Task 1: Repository, settings, local database, CI

**Files:** `pyproject.toml`, `Makefile`, `docker-compose.yml` (postgres:17, port 5435, databases `weather_api` and `weather_api_test`), `.gitignore`, `.github/workflows/ci.yml` (Python 3.12, postgres service, `make check`), `README.md` (stub), `CLAUDE.md`, `src/weather_api/__init__.py`, `src/weather_api/config.py`, `tests/conftest.py`, `tests/test_config.py`

**Interfaces — produces:** `class Settings(BaseSettings)`: `database_url: str` (env `DATABASE_URL`), `marts_url: str` (default the source URL), `cache_check_seconds: int = 60`; `def get_settings() -> Settings`. `tests/conftest.py` fixture `engine` (test database from `TEST_DATABASE_URL`, default `postgresql+psycopg://postgres:postgres@localhost:5435/weather_api_test`).

- [ ] Step 1: failing `test_settings_read_the_environment` (monkeypatch `DATABASE_URL`, assert `get_settings().database_url`). Run → FAIL. Implement. Run → PASS.
- [ ] Step 2: `docker compose up -d db`; `make check` green; commit "Start the weather API: package, settings, local database, CI".

### Task 2: Schema and migrations

**Files:** `src/weather_api/db.py`, `alembic.ini`, `migrations/` (env.py reads `DATABASE_URL`), `migrations/versions/0001_initial.py`, `tests/test_schema.py`

**Interfaces — produces:** SQLAlchemy Core tables in `db.py`: `locations(location_code PK, town, territory, latitude, longitude)`, `daily_weather(location_code FK, observed_date, temp_min_c, temp_max_c, temp_avg_c, rain_total_mm, wind_max_kmh, hours_observed; PK(location_code, observed_date))`, `daily_air_quality(… pm10_avg_ugm3, pm10_max_ugm3, pm2_5_avg_ugm3, dust_max_ugm3, ozone_max_ugm3, european_aqi_max, exceeds_pm10_daily_limit, hours_observed; same PK)`, `loads(id, generated_at UNIQUE, loaded_at, locations, weather_rows, air_quality_rows)`, `api_keys(id, name UNIQUE, key_hash UNIQUE, per_minute, created_at, revoked_at NULL)`; index on `(observed_date, location_code)` for both daily tables. `conftest.py` applies `alembic upgrade head` once per session and truncates tables between tests.

- [ ] Step 1: failing `test_migration_creates_the_tables` (inspect: five tables, the PKs, the index). Run → FAIL. Implement. PASS. Commit "Describe the database with a first migration".

### Task 3: Loading `marts.json`

**Files:** `src/weather_api/marts.py`, `src/weather_api/load.py`, `src/weather_api/cli.py` (`load`), `tests/fixtures/marts.json` (2 towns, 3 days, the last day partial), `tests/test_load.py`

**Interfaces — produces:** Pydantic `Marts`, `Location`, `DailyWeather`, `DailyAirQuality` (fields as the contract); `def fetch_marts(client: httpx.Client, url: str) -> Marts`; `@dataclass LoadResult(skipped: bool, locations: int, weather_rows: int, air_quality_rows: int)`; `def load_marts(engine: Engine, marts: Marts) -> LoadResult`.

- [ ] Step 1: failing tests:
  - `test_load_inserts_every_row` (counts equal the fixture);
  - `test_same_file_twice_is_skipped` (second result `skipped=True`, tables unchanged);
  - `test_newer_file_updates_and_deletes_vanished_rows` (a row changed, a row removed from the file → removed from the table);
  - `test_invalid_file_writes_nothing` (a row with `territory: "Cuba"` → `ValidationError`, tables still empty);
  - `test_fetch_reads_the_published_file` (respx on the source URL).
- [ ] Step 2: FAIL → implement (one transaction: upsert locations, upsert daily rows with `ON CONFLICT DO UPDATE`, delete rows absent from the file, insert into `loads`) → PASS. CLI `weather-api load` prints the result. Commit "Load the batch marts into PostgreSQL".

### Task 4: API keys

**Files:** `src/weather_api/keys.py`, `cli.py` (`keys create|revoke|list`), `tests/test_keys.py`

**Interfaces — produces:** `KEY_PATTERN = re.compile(r"^aw_[A-Za-z0-9_-]{43}$")`; `def hash_key(key: str) -> str` (hex SHA-256); `def create_key(engine, name: str, per_minute: int) -> str` (returns the plaintext once); `def revoke_key(engine, name: str) -> bool`; `def list_keys(engine) -> list[KeyInfo]` (`name, per_minute, created_at, revoked_at`); `def find_key(engine, key_hash: str) -> KeyInfo | None` (active keys only).

- [ ] Step 1: failing tests: `test_created_key_matches_the_pattern_and_only_its_hash_is_stored`; `test_revoked_key_is_not_found`; `test_list_never_shows_keys`; `test_duplicate_name_is_refused`. FAIL → implement → PASS. Commit "Create, revoke and list API keys".

### Task 5: App, access control, health and meta

**Files:** `src/weather_api/app.py` (`create_app(settings, engine) -> FastAPI`, `app` for uvicorn), `src/weather_api/access.py`, `src/weather_api/problems.py`, `src/weather_api/routes/meta.py` (`/health`, `/v1/meta`, `/v1/locations`, `/v1/locations/{code}`), `tests/test_access.py`, `tests/test_meta.py`

**Interfaces — produces:** `class KeyCache(ttl_seconds=60, clock=time.monotonic)`; `class RateLimiter(window_seconds=60, clock=time.monotonic)` with `def hit(key_hash: str, limit: int) -> tuple[bool, int, int]` (allowed, remaining, retry_after); dependency `require_key` (format → cache → `find_key` → limiter; sets the RateLimit headers); `problem(status, title, detail) -> JSONResponse`; `class DataUnavailable(Exception)` → 503 problem.

- [ ] Step 1: failing tests (TestClient, fake clock):
  - `test_missing_unknown_and_revoked_keys_get_401_problem`;
  - `test_malformed_key_is_rejected_without_a_query` (engine wrapped to count `execute` calls → 0);
  - `test_quota_returns_429_with_retry_after` (limit 2: third call 429, `Retry-After` > 0, `RateLimit-Remaining: 0`; window passes → 200);
  - `test_revoked_key_works_until_the_cache_expires` (Review Focus 4: 200 at +59 s, 401 at +61 s);
  - `test_health_reports_the_database` (200; with an engine on a closed port → 503, Review Focus 3);
  - `test_no_data_loaded_yet_is_503` (empty tables → `/v1/meta` 503 problem, Review Focus 5);
  - `test_meta_and_locations` (after loading the fixture: `generated_at`, six fields per town; unknown town → 404 problem);
  - `test_cors_allows_get_from_anywhere`.
- [ ] Step 2: FAIL → implement → PASS. Commit "Serve towns and metadata behind API keys and quotas".

### Task 6: Data routes and response cache

**Files:** `src/weather_api/routes/data.py`, `src/weather_api/queries.py`, `src/weather_api/cache.py`, `tests/test_data.py`, `tests/test_cache.py`

**Interfaces — produces:** `GET /v1/weather`, `GET /v1/air-quality` (params `location: list[str]`, `start`, `end`, `limit`, `cursor`; body `{"items": [...], "next_cursor": str | null}`); `GET /v1/locations/{code}/summary?days=` (body: `days, start, end, temp_avg_c, rain_total_mm, pm10_avg_ugm3, dust_peak {value, date} | null, days_above_pm10_limit, previous {same fields} | null`); `GET /v1/dust-episodes` (`items` of `{location_code, observed_date, pm10_avg_ugm3, dust_max_ugm3}`); `class ResponseCache` keyed by (path, sorted query), cleared when `/v1/meta`'s `generated_at` changes (checked at most every `cache_check_seconds`). Cursor = url-safe base64 of `"<date>|<code>"`.

- [ ] Step 1: failing tests (fixture loaded):
  - `test_partial_days_are_never_served` (the fixture's last day absent from weather, air quality, summary);
  - `test_pagination_walks_every_row_once` (`limit=2` until `next_cursor` is null = all complete rows, no duplicate);
  - `test_filters_by_town_and_dates` (`start > end` → 422);
  - `test_garbled_cursor_is_422` (Review Focus 1);
  - `test_unknown_town_in_filter_is_404` (Review Focus 2);
  - `test_summary_values` (exact means, totals, peak and count over the fixture's complete days; `latest` = last complete day; `days=10` → 422);
  - `test_dust_episodes_list_days_above_the_limit`;
  - `test_cache_serves_without_the_database_until_new_data` (second identical call: 0 queries; after a new load and the check interval: fresh data).
- [ ] Step 2: FAIL → implement → PASS. Commit "Serve weather, air quality, summaries and dust episodes".

### Task 7: Image, infrastructure and workflows

**Files:** `Dockerfile` (multi-stage, non-root, `uvicorn weather_api.app:app --port $PORT`), `.dockerignore`, `infra/{main,variables,outputs}.tf`, `infra/README.md`, `.github/workflows/deploy.yml` (on push to `main`: test, `alembic upgrade head` with `secrets.DATABASE_URL`, build and push to Artifact Registry, `gcloud run deploy`), `.github/workflows/daily.yml` (11:00 UTC + manual: `weather-api load`)

- [ ] Step 1: `docker build` and run the image against the local database: `/health` 200, `/docs` 200.
- [ ] Step 2: Terraform: Artifact Registry repo `weather-api` (us-east4, keep the 5 latest images), secret `weather-api-database-url`, service accounts `api-deployer` (run.admin, artifactregistry.writer, iam.serviceAccountUser on the runtime account) and `weather-api` (secretAccessor on the secret), a WIF provider `github-weather-api` for `tomtessondev/antilles-weather-api`, Cloud Run service (min 0, max 2, 1 vCPU, 512 MiB, `allUsers` invoker, the secret as `DATABASE_URL`). `terraform validate`; plan to the owner. **Owner approval → apply.**
- [ ] Step 3: **Owner action**: create the Neon project (AWS us-east-1), give the connection string; store it as the secret's version and as GitHub secret `DATABASE_URL`. Commit "Deploy to Cloud Run with keyless CI".

### Task 8: Publication, demo key, docs and portfolio

- [ ] Step 1: README (story, architecture diagram, routes with curl examples, access and quotas, why Neon sleeps, cost, run locally), `docs/ROADMAP.md`; `make check`; commit.
- [ ] Step 2: **Owner approval** → `gh repo create tomtessondev/antilles-weather-api --public`, push, repository variables (`GCP_SERVICE_ACCOUNT`, `GCP_WORKLOAD_IDENTITY_PROVIDER`), secret `DATABASE_URL`; PR, CI green, merge on the owner's go; first deploy; `weather-api load` once; create the demo key (60/min) and put it in the README and the OpenAPI description; check `/docs` live and a cold call.
- [ ] Step 3: in `antilles-data-pipeline` (branch `docs/weather-api`): `dashboard/src/lib/portfolio.ts` sixth project (family "API", colour token `--family-api` light/dark validated), page `/projets/antilles-weather-api` on `ProjectLayout` with its architecture diagram, every "cinq" → "six" (home, metadata, glossary, facts), glossary terms (API REST, clé d’API, quota, pagination, OpenAPI, migration), `docs/ROADMAP.md` API step done; dashboard checks, `make check`, `make transform`; PR after the owner's go. Portfolio root `README.md` and `CLAUDE.md` (row, ports, Neon).
