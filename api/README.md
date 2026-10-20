# DataRepo — api

Flask backend of DataRepo: authentication and users, audit trail, tables,
views, saved and materialized reports, read-only SQL queries, managed SQL
functions and external connections through FDW. It also owns the database
**migrations** (Alembic) and the compose files in `deploy/`.

```
app.py              builds the Flask app: one blueprint per domain
routes/             identity, audit, catalog, query, functions, connections
services/           business rules and SQL
kit/  db.py         code shared with ingestion (JWT, audit, SQL guard...)
migrations/         Alembic (system tables)
deploy/             docker-compose files and deploy scripts
docs/               architecture, data, API, database
```

## Run

See the [root README](../README.md#run-locally). Tests: `pip install -r requirements-dev.txt && python -m pytest -q`.

## Docs

[Architecture](docs/ARCHITECTURE.md) · [Data](docs/DATA.md) · [API](docs/API.md) · [Database](docs/database/README.md)
