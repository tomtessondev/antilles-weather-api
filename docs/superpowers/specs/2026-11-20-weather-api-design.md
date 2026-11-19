# Antilles weather API — design

## Intent

The sixth portfolio project (phase 4 roadmap of `antilles-data-pipeline`: "API service — serve
the marts through a typed REST API with auth and tests"). The batch project already prepares
daily weather and air-quality marts for six towns of Guadeloupe and Martinique and publishes
them every morning as `marts.json` on the `data` branch of its repository. This project serves
those marts to other applications through a real, documented, authenticated REST API, online,
so that a recruiter or a client can call it from the browser. It shows what freelance missions
ask after the pipeline: serving data — schema and indexes, migrations, typed contracts,
filtering and pagination, authentication and quotas, tests against a real database, a Docker
image deployed to the cloud with keyless CI.

## Goals

- New public repository `antilles-weather-api` (Python 3.12, FastAPI, Pydantic v2,
  SQLAlchemy 2 with psycopg 3, Alembic, uvicorn; ruff, mypy `--strict`, pytest).
- **Loading**: a command `weather-api load` downloads `marts.json`
  (`https://raw.githubusercontent.com/tomtessondev/antilles-data-pipeline/data/marts.json`),
  validates it with Pydantic (same fields as `dashboard/src/lib/schema.ts` of the batch
  project), and upserts locations, daily weather and daily air quality in one transaction.
  Idempotent: the same file loaded twice changes nothing; a file whose `generated_at` is
  already loaded is skipped. Each load is recorded (`generated_at`, `loaded_at`, row counts).
  Run daily by GitHub Actions at 11:00 UTC (the batch export runs at 10:00 UTC) and on demand.
- **API** (read-only, versioned under `/v1`, JSON):
  - `GET /v1/locations`, `GET /v1/locations/{code}`;
  - `GET /v1/weather` and `GET /v1/air-quality`: filters `location` (repeatable), `start`,
    `end` (ISO dates, inclusive); keyset pagination ordered by (`observed_date`,
    `location_code`) with `limit` (default 100, max 500) and an opaque `cursor`, the next one
    returned in the response;
  - `GET /v1/locations/{code}/summary?days=7|14|30`: over the latest `days` complete days,
    mean temperature, rain total, mean PM10, highest dust peak (value and date), days above
    the EU PM10 daily limit (50 µg/m³), and the change versus the `days` before;
  - `GET /v1/dust-episodes?start&end&location`: days where a town's PM10 daily mean exceeds
    the EU limit, with the dust peak;
  - `GET /v1/meta`: `generated_at` of the data served and time of the last load;
  - `GET /health` (no key): the process answers and the database answers.
  - Errors as `application/problem+json` (RFC 9457) with English messages (`title`,
    `status`, `detail`), like the rest of the API; 401 for a missing, unknown or revoked key,
    404 for an unknown town, 422 for invalid parameters, 429 over quota.
- **Access**: every `/v1` call needs a key in the `X-API-Key` header.
  - Keys look like `aw_<43 url-safe chars>`; only their SHA-256 is stored, with a name, a
    per-minute quota, creation and revocation times.
  - `weather-api keys create --name <n> --per-minute <q>` prints the key once;
    `weather-api keys revoke <name>`; `weather-api keys list` (never prints keys).
  - Quota: a fixed one-minute window per key (counted in memory, see "My calls"); beyond
    it, 429 with `Retry-After`; every response carries `RateLimit-Limit` and
    `RateLimit-Remaining`.
  - A **public demo key** (60 requests per minute) is printed in the README, on the French
    project page and in the OpenAPI description, so anyone can try the API from `/docs`.
- **Documentation**: the OpenAPI schema and Swagger UI at `/docs` (FastAPI), with
  descriptions and examples for every route; README with a curl example, the architecture,
  the cost and the access model.
- **Deployment**: Google Cloud Run (scale to zero, max 2 instances, 1 vCPU, 512 MiB) running
  the Docker image from Artifact Registry; the database is a Neon free-plan PostgreSQL. The
  image is built and deployed by GitHub Actions on every push to `main`, authenticating with
  Workload Identity Federation (no key). The database URL lives in Secret Manager and is
  mounted into the service; the daily load reads it from a GitHub secret.
- **Portfolio**: French page `/projets/antilles-weather-api` on the template (architecture
  diagram, En bref box), a sixth entry in `dashboard/src/lib/portfolio.ts` (the home page,
  sidebar, skills grid and previous / next follow), every "cinq projets" text on the site
  becomes "six", the roadmap step marked done, glossary terms (API REST, clé d'API, quota,
  pagination, OpenAPI, migration), portfolio root `README.md` and `CLAUDE.md`.

## Non-goals

- Writing data through the API; user sign-up or self-service keys; OAuth / JWT for end users.
- Other projects' data (hurricane passages, climate series, ships) — possible later.
- GraphQL, websockets, a front-end of its own (Swagger UI is the front-end).

## Anti-goals

- A bill: anything that could leave the free tiers unnoticed (min instances above zero,
  unbounded instances, an always-on database).
- Secrets in the repository, in the image or in logs; long-lived cloud keys in GitHub.
- An API that breaks when the batch pipeline stops: it keeps serving the last loaded data and
  says how old it is (`/v1/meta`).
- Tests that call GitHub, Google Cloud or Neon.

## Constraints

- GCP project `antilles-hurricanes` (billing in USD, 5 USD monthly budget with alerts, owner
  approves every `terraform apply`); region `us-east4` for Cloud Run and Artifact Registry,
  Neon in AWS `us-east-1` (same area, lowest latency).
- Neon free plan: 1 GB storage, 100 CU-hours a month, compute suspended after 5 minutes idle
  (first query after idle waits for it to wake). Cloud Run free tier: about 2 million
  requests and 180,000+ vCPU-seconds a month. A cold call may take 1 to 2 s; accepted.
- The owner creates the Neon account and project by hand (free, no card) and gives the
  connection string; everything on GCP is Terraform.
- Repository rules as in the other projects: English code and docs, `make check` before
  every commit, one pull request per feature, never call real external services in tests.

## Approaches

1. **Daily copy into Neon, the API reads PostgreSQL** (chosen by the owner): real schema,
   migrations, filtered and paginated SQL, tests against PostgreSQL; the batch project is
   untouched.
2. The API keeps `marts.json` in memory, no database: simplest, but nothing to show beyond a
   file relay, and it contradicts the roadmap (PostgreSQL).
3. The API reads the batch S3 lake with DuckDB: full history, but a long-lived AWS key in
   Cloud Run and a dependency on an AWS free plan that ends in May 2027.

Hosting, decided with the owner: Cloud Run + Neon (free) over Railway (about 5 USD a month),
Vercel functions (no real container) and Render free (sleeps 30 s, database expires after
30 days).

## Decided

- Approach 1; hosting Cloud Run + Neon; online, callable by anyone with the demo key (owner).
- Access by API key in `X-API-Key`, hashed, per-key quota, public demo key (proposed, owner
  agreed to the approach that included it).

## My calls (the owner can correct them)

- Repository name `antilles-weather-api`; package `weather_api`; CLI `weather-api`.
- Reuse GCP project `antilles-hurricanes` (its budget and WIF pool already exist) with a new
  service account `api-deployer` (deploy) and `weather-api` (runtime: read the secret only);
  the WIF provider gains this repository.
- Tests run against a real PostgreSQL: Docker Compose locally, a service container in CI;
  migrations applied at test start; HTTP to GitHub mocked with respx.
- CORS: `GET` allowed from any origin (a public read API).
- No cache layer: the data is small and changes once a day; responses carry
  `Cache-Control: public, max-age=300`.
- Dates are ISO strings; numbers are JSON numbers with the units in field names, as in the
  marts (`temp_max_c`, `pm10_avg_ugm3`).

- **Complete days only.** `marts.json` ends with partial days (today and a forecast day,
  `hours_observed < 24`, rewritten by later runs). The API serves only days with
  `hours_observed = 24` for both measures of that table; "latest" means the latest complete
  day loaded, never today, so summaries stay full when the pipeline stops. Partial rows are
  still loaded (they become complete on a later run) but filtered out at query time.
- **Rows that vanish from the marts** are deleted by the load (the file is the full state),
  inside the same transaction.
- **Keep Neon asleep under public traffic.** Neon's free compute (100 CU-hours a month) runs
  out if every request wakes the database. So: (1) a key that does not match the `aw_`
  format is rejected without a query; (2) valid key hashes are cached in memory for 60 s;
  (3) the quota is counted in memory per instance (fixed one-minute window; with at most two
  instances a key gets at most twice its quota, accepted and documented); (4) data responses
  are cached in memory until the next load (`/v1/meta` `generated_at` checked at most once a
  minute). This replaces "counted in PostgreSQL" above: the database is touched only by the
  daily load, cache misses and `keys` commands.
- **WIF**: the API repository gets its own provider in the existing `github` pool, in its own
  Terraform state (`gs://antilles-hurricanes-tfstate`, prefix `weather-api`); the warehouse's
  Terraform and provider are not touched.
- Migrations run from GitHub Actions before each deploy (`alembic upgrade head` against the
  Neon URL), not at container start.

## Left to the builder

- The SQL of the summary and dust-episode queries; the cursor encoding.
- The Alembic layout; the Dockerfile (multi-stage, non-root user).
- The exact Terraform resources for Artifact Registry, Secret Manager and Cloud Run IAM.
