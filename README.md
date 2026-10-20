# DataRepo

A small data-hub web application: upload spreadsheets and PDFs into PostgreSQL
tables, browse and query them, save reports, materialize views, manage SQL
functions and reach external databases through foreign data wrappers — with
authentication, roles and a full audit trail.

It is a monorepo of three deployable services:

| Directory | Service | What it does |
|---|---|---|
| [`api/`](api) | `api`, `api-query` | Flask backend: auth and users, audit trail, tables, views, saved and materialized reports, read-only SQL queries, managed SQL functions, FDW connections. Owns the Alembic migrations. `api-query` is the same image, serving only `/api/v1/query`. |
| [`ingestion/`](ingestion) | `ingestion` | Upload and parsing of Excel, CSV and PDF into data tables. |
| [`web/`](web) | `web` | React + Vite single-page app, served by an nginx edge that routes `/api` to the three backends. |

PostgreSQL is **not** part of the stack: point `DATABASE_URL` at an existing
server (requirements in [`api/docs/database`](api/docs/database/README.md)).

## Run locally

```bash
cd api/deploy && cp .env.example .env     # fill in the secrets
C="docker compose -f docker-compose.app.yml -f docker-compose.dev.yml"
$C up -d --build db && $C run --rm api alembic upgrade head && $C up -d --build
```

The app is served at <http://localhost:5173>.

## Tests

```bash
(cd api && pip install -r requirements-dev.txt && python -m pytest -q)
(cd ingestion && pip install -r requirements-dev.txt && python -m pytest -q)
(cd web && npm ci && npm test)
```

## Docs

[Architecture](api/docs/ARCHITECTURE.md) · [Data model](api/docs/DATA.md) ·
[API](api/docs/API.md) · [Database requirements](api/docs/database/README.md).
Most documentation is written in Brazilian Portuguese.

## License

Apache-2.0 — see [LICENSE](LICENSE).
