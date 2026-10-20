# Data Layer

Single Postgres 15 database `data_app`, **outside** the application's compose
(`DATABASE_URL`; requirements in `docs/database/`), shared by `api` and
`ingestion`. Two classes of tables:

1. **System tables** — prefixed `_system_` / `_` (or `audit_log`); schema owned by
   the Alembic migrations in `migrations/` (control table `_alembic_version`).
   Hidden from `GET /api/v1/tables`.
2. **User tables** — created dynamically from Excel/CSV/PDF uploads by
   `ingestion`; renamed and dropped by `api`. Visible in the listing. Never
   touched by migrations.

## Who writes what

| Table / object | Written by |
|---|---|
| `_system_users`, `_system_password_resets`, `audit_log`, `_system_reports`, `_system_materialized_views`, `_view_history`, `_system_functions`, `_system_connections`, views, `fn_*`, FDW servers, `ext_*` schemas | api |
| user data tables (create, append rows), `_column_aliases` | ingestion (api reads aliases; renames/drops tables) |
| `audit_log` rows for uploads | api, on behalf of ingestion (`POST /internal/v1/events`) |

## Schema

### `_system_users`

```
id              SERIAL PK
username        TEXT UNIQUE NOT NULL
password_hash   TEXT NOT NULL
can_query                BOOL DEFAULT FALSE
can_upload               BOOL DEFAULT FALSE
can_manage_views         BOOL DEFAULT FALSE
can_manage_functions     BOOL DEFAULT FALSE
can_manage_users         BOOL DEFAULT FALSE
can_view_audit           BOOL DEFAULT FALSE   -- added via ALTER, post-launch
can_manage_connections   BOOL DEFAULT FALSE   -- added via ALTER, post-launch
created_at      TIMESTAMP DEFAULT now()
```

Historically the monolith issued `CREATE TABLE IF NOT EXISTS` plus `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for `can_manage_functions`, `can_view_audit`, and `can_manage_connections`, plus backfill UPDATEs granting `can_manage_functions` and `can_manage_connections` to existing admins.

### `_system_password_resets`

```
id            BIGSERIAL PK
user_id       INT NOT NULL REFERENCES _system_users(id) ON DELETE CASCADE
token_hash    TEXT UNIQUE NOT NULL   -- SHA-256 of the token; the token itself is never stored
expires_at    TIMESTAMPTZ NOT NULL   -- now() + 30 min, always compared server-side
used_at       TIMESTAMPTZ            -- set when consumed, or when superseded by a newer request
created_at    TIMESTAMPTZ DEFAULT now()
ip            TEXT

indexes:
  idx_password_resets_user (user_id)
```

Single use: consuming a token is one `UPDATE ... WHERE used_at IS NULL AND expires_at > now() RETURNING user_id`, so concurrent requests cannot both win. Requesting a new link marks any outstanding token for that user as used. The api deletes rows expired for more than a day on startup (`purge_expired_resets`).

### `_system_reports`

```
id           SERIAL PK
name         VARCHAR(255) UNIQUE NOT NULL
description  TEXT
sql_query    TEXT NOT NULL
created_at   TIMESTAMP DEFAULT now()
```

### `_system_functions`

```
id              SERIAL PK
name            TEXT UNIQUE NOT NULL          -- display name
function_name   TEXT UNIQUE NOT NULL          -- 'fn_<slug>', actual PG function name
description     TEXT
kind            TEXT CHECK (kind IN ('scalar','table'))
parameters      JSONB DEFAULT '[]'
return_type     TEXT
return_columns  JSONB DEFAULT '[]'            -- only for kind='table'
sql_body        TEXT NOT NULL
created_at      TIMESTAMP DEFAULT now()
updated_at      TIMESTAMP DEFAULT now()
```

Two-phase write: row in `_system_functions` AND a real PG `CREATE FUNCTION fn_<slug> ...` in the `public` schema. Update = `DROP FUNCTION` + `CREATE FUNCTION`.

### `_view_history`

```
id              SERIAL PK
view_name       TEXT NOT NULL
view_definition TEXT NOT NULL
operation       TEXT NOT NULL              -- e.g. 'created','renamed','dropped','restored'
related_to      TEXT
dropped_at      TIMESTAMP DEFAULT now()
```

Captured by `smart_update_view` so dependent views can be reattached after a parent rename/drop cascade.

### `_system_connections`

```
id              SERIAL PK
name            TEXT UNIQUE NOT NULL          -- slug; materialized as schema "ext_<name>" + server "conn_<name>"
display_name    TEXT NOT NULL
db_type         TEXT CHECK (db_type IN ('sqlserver','postgres'))
host            TEXT NOT NULL
port            INTEGER NOT NULL
database        TEXT NOT NULL
remote_schema   TEXT                          -- 'dbo' (sqlserver) or 'public' (postgres) by default
username        TEXT NOT NULL
password_enc    TEXT NOT NULL                 -- Fernet ciphertext (CONNECTIONS_ENCRYPTION_KEY)
options         JSONB DEFAULT '{}'
last_synced_at  TIMESTAMPTZ
created_at      TIMESTAMPTZ DEFAULT now()
updated_at      TIMESTAMPTZ DEFAULT now()
```

Migration `0001` also creates the `tds_fdw`, `postgres_fdw` and `pg_cron` extensions when available. Each row is paired with PG `SERVER conn_<name>` + `USER MAPPING FOR CURRENT_USER` + foreign tables imported into schema `ext_<name>` so they can be referenced in regular SELECT/JOIN queries alongside `public.*` and `fn_*()`.

### `audit_log`

```
id            BIGSERIAL PK
ts            TIMESTAMPTZ DEFAULT now()
user_id       INT REFERENCES _system_users(id) ON DELETE SET NULL
username      TEXT                 -- snapshot, survives user deletion
action        TEXT NOT NULL        -- CREATE|UPDATE|DELETE|UPLOAD|RENAME|LOGIN|ANALYZE|QUERY
entity_type   TEXT NOT NULL        -- user|report|view|table|table_row|file|session|function
entity_id     TEXT
before_state  JSONB
after_state   JSONB
metadata      JSONB                -- ip, user_agent, summary {rows, table_name, filename}
status        TEXT DEFAULT 'success'  -- success|failed
error         TEXT

INDEXES:
  idx_audit_log_ts     (ts DESC)
  idx_audit_log_user   (user_id)
  idx_audit_log_entity (entity_type, entity_id)
  idx_audit_log_action (action)
```

`before_state` / `after_state` / `metadata` are passed through `redact()` (scrubs `password`, `password_hash`, `token`, `secret`) and truncated at 64 KB before insert.

## Relationships

```
_system_users.id ◄──── audit_log.user_id                  (SET NULL on delete)
_system_users.id ◄──── _system_password_resets.user_id   (CASCADE on delete)
```

No other FKs. Reports / functions / views reference each other only via name strings; integrity is enforced at the application layer.

## Migrations

Alembic, in `migrations/`, **hand-written, no autogenerate** (autogenerate would
treat user tables and views as drift and propose dropping them).

- `0001` — the exact DDL the monolith ran on every boot (`init_*_table()`), all
  `IF NOT EXISTS`. On the existing production database it changes nothing and
  only records the version; on an empty database it builds the full schema.
  `tools/check-migrations.sh` proves both against a real Postgres.

Applied by the api deploy (`alembic upgrade head`) before the containers are
replaced. Every migration must be compatible with the previous code version,
because an image rollback does not revert migrations.

## DB access pattern

`db.py` (shared by api and ingestion through the kit):
- `get_db_connection()` — SQLAlchemy engine (singleton, `pool_pre_ping=True`).
- `execute_query(sql, params=None)` — read-write, returns dict rows.
- `execute_readonly_query(sql, statement_timeout_ms=30000)` — opens a connection with `default_transaction_read_only=on` and a `SET LOCAL statement_timeout`. Used for `/query` and `/reports/<id>/execute`.
- `convert_to_serializable(value)` — coerces datetimes, Decimal, etc. for JSON output. Reused inside `audit_service`.

## Connection string

`DATABASE_URL` in the host `.env` (e.g. `postgresql://user:password@db:5432/data_app`), passed to api, api-query and ingestion. The database itself is managed outside this project.
