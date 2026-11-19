# Antilles Weather API

[![CI](https://github.com/tomtessondev/antilles-weather-api/actions/workflows/ci.yml/badge.svg)](https://github.com/tomtessondev/antilles-weather-api/actions/workflows/ci.yml)
[![Deploy](https://github.com/tomtessondev/antilles-weather-api/actions/workflows/deploy.yml/badge.svg)](https://github.com/tomtessondev/antilles-weather-api/actions/workflows/deploy.yml)

A public REST API over the daily weather and air quality of six towns of Guadeloupe and
Martinique. The data comes from the marts of
[antilles-data-pipeline](https://github.com/tomtessondev/antilles-data-pipeline), loaded every
morning into PostgreSQL; the API is FastAPI on Google Cloud Run, the database is Neon, and
both stay inside their free tiers.

**Try it:** [interactive documentation](https://weather-api-v4mw6h4rqa-uk.a.run.app/docs) —
click *Authorize* and paste the demo key:

```text
DEMO_KEY
```

```bash
curl -H "X-API-Key: DEMO_KEY" \
  "https://weather-api-v4mw6h4rqa-uk.a.run.app/v1/locations/FDF/summary?days=7"
```

The demo key allows 60 requests a minute. The first call after a quiet spell can take a
second or two: the service and the database wake up.

## Routes

| Route | What it returns |
| --- | --- |
| `GET /v1/locations`, `/v1/locations/{code}` | The six towns (code, name, island, coordinates) |
| `GET /v1/weather` | Daily temperature, rain and wind per town |
| `GET /v1/air-quality` | Daily PM10, PM2.5, Saharan dust, ozone, European AQI |
| `GET /v1/locations/{code}/summary?days=7\|14\|30` | A town's latest days against the days before: mean temperature, rain, mean PM10, dust peak, days above the EU limit |
| `GET /v1/dust-episodes` | Days whose PM10 daily mean is above the EU limit (50 µg/m³) |
| `GET /v1/meta` | When the data served was produced and loaded |
| `GET /health` | The service and its database answer (no key) |

The daily routes filter by `location` (repeatable), `start` and `end` (ISO dates, inclusive)
and page with `limit` (up to 500) and the `next_cursor` of the previous page. Only complete
days are served: the export's last day is still being measured and its forecast day is not
a measurement. Errors are [problem details](https://www.rfc-editor.org/rfc/rfc9457) (`401`
key, `404` unknown town, `422` bad parameter, `429` quota, `503` database unavailable).

## Architecture

```text
antilles-data-pipeline (10:00 UTC)  →  marts.json on its `data` branch
                                            │  GitHub Actions, 11:00 UTC: weather-api load
                                            ▼
                          Neon PostgreSQL (free plan, sleeps when idle)
                                            ▲  SQL on a cache miss only
Callers  ── X-API-Key ──►  Cloud Run: FastAPI (0 to 2 instances, scales to zero)
                                            ▲
GitHub Actions on main: tests → migrations → image → Artifact Registry → deploy (no key)
```

- **Loading** (`weather-api load`): download, validate with Pydantic, then one transaction:
  upsert towns and days, delete what the file no longer holds, record the load. The same
  file twice changes nothing; an invalid file writes nothing.
- **Access**: keys look like `aw_…`; only their SHA-256 is stored. `weather-api keys create
  --name <client> --per-minute <n>` prints a key once; `revoke` and `list` manage them.
- **Keeping the database asleep**: Neon's free compute would run out if every request woke
  it. A malformed key is refused on its shape, known keys are cached for a minute, the quota
  is counted in memory (per instance: with two instances a key gets at most twice its
  quota), and answers are cached until the next load. Between loads, repeated calls never
  reach the database.

## Cost

| Piece | Free allowance | Use |
| --- | --- | --- |
| Cloud Run | about 2 million requests and 180,000 vCPU-seconds a month | scales to zero, at most 2 instances, CPU billed only during requests |
| Neon | 1 GB, 100 compute-hours a month | about 50 KB of data; awake only for loads and cache misses |
| Artifact Registry | 0.5 GB | the two latest images (about 370 MB each): a few cents a month |
| Secret Manager | 6 secret versions | one |

The Google Cloud project has a 5 USD monthly budget with alerts at 50, 90 and 100 %.

## Run it locally

```bash
python3.12 -m venv .venv && source .venv/bin/activate
make install
make db                 # PostgreSQL in Docker on port 5435
make check              # ruff, mypy --strict, pytest (against that database)
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5435/weather_api make migrate load run
```

Tests run against a real PostgreSQL and never call GitHub, Google Cloud or Neon. The Google
Cloud side is Terraform in [`infra/`](infra/README.md).

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md).
