# API Reference

HTTP API for DataRepo. All routes are under `/api/v1` and are served through
the nginx of `datarepo-web`, which routes each path prefix to a container.
The paths did not change with the split (ADR 0004).

> **Base URL** — `http://<host>:5173` or `http://<host>:5000` (both ports reach
> the same nginx).

| Prefix | Container (repository) |
|---|---|
| `/query` | `api-query` (DataRepo — same image as `api`) |
| `/upload`, `/map-file`, `/inspect-headers`, `POST /tables/<t>/data` | `ingestion` (datarepo-ingestion) |
| everything else | `api` (DataRepo) |

The authoritative mapping is `datarepo-web/tests/routes.tsv`, checked
against the real nginx and against the routes the api and ingestion declare.

`/internal/*` routes are service-to-service only and are never reachable through
the nginx.

## Authentication

All endpoints require a bearer JWT except the public auth routes: `POST /auth/login`, `POST /auth/forgot-password` and `POST /auth/reset-password`.

```
Authorization: Bearer <token>
```

Tokens are HS256, signed with `JWT_SECRET`, TTL **12 hours**. Obtain one via `POST /api/v1/auth/login`.

### Permission flags

Each user has a permissions object with these boolean flags (`kit/auth.py`, shared by every service):

| Flag                    | Grants                                                   |
|-------------------------|----------------------------------------------------------|
| `can_query`             | Run ad-hoc `SELECT` queries via `/query`                 |
| `can_upload`            | Upload Excel, append rows, analyze file structure        |
| `can_manage_views`      | Create/edit/delete views, reports, rename/delete tables  |
| `can_manage_functions`  | Manage SQL functions in `_system_functions`              |
| `can_manage_users`      | List/create/update/delete users                          |
| `can_view_audit`        | Read the audit log                                       |

The seeded admin user gets all flags set to `true`.

## Error envelope

Errors return a JSON body and a non-2xx status. 500 responses are sanitized — the real exception is recorded in the audit log instead of leaked to the client:

```json
{ "error": "Invalid credentials" }
```

## Endpoints

### Auth

#### `POST /api/v1/auth/login`

Public. Rate-limited to **10 req/min per IP**.

```bash
curl -X POST http://localhost:5000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"change-me"}'
```

Response `200`:
```json
{
  "token": "eyJhbGci…",
  "user": { "id": 1, "username": "admin", "perms": { "can_query": true, "...": true } }
}
```

Login attempts (success and failure) are written to the audit log with IP and User-Agent.

#### `GET /api/v1/auth/me`

Returns the current user record.

#### `POST /api/v1/auth/forgot-password`

Public. Rate-limited to **5 req/min per IP**. Starts the self-service password reset:
issues a single-use token (valid for **30 minutes**) and e-mails a link to the account,
whose username is also its e-mail address.

```bash
curl -X POST http://localhost:5000/api/v1/auth/forgot-password \
  -H 'Content-Type: application/json' \
  -d '{"username":"fulano@example.com"}'
```

Always responds `200` with the same body, whether or not the account exists, so the
endpoint cannot be used to enumerate usernames:

```json
{ "message": "If the account exists, a reset link has been sent" }
```

A missing `username` returns `400`. Usernames that are not e-mail addresses (such as a
seeded `admin`) get the generic `200` but no e-mail — those accounts are reset by an
administrator through `PUT /api/v1/users/<id>`.

The link points at `<APP_BASE_URL>/reset-password/<token>`; when `APP_BASE_URL` is unset
the origin is taken from the request (`X-Forwarded-Proto` / `X-Forwarded-Host`).
Delivery happens on a background thread, so a slow or failing SMTP server never changes
the response — failures are recorded in the audit log as `PASSWORD_RESET_REQUEST`.

#### `POST /api/v1/auth/reset-password`

Public. Rate-limited to **10 req/min per IP**. Consumes the token from the e-mail and
sets the new password. Tokens are single-use and expire after 30 minutes.

```bash
curl -X POST http://localhost:5000/api/v1/auth/reset-password \
  -H 'Content-Type: application/json' \
  -d '{"token":"<token>","password":"nova-senha-forte"}'
```

Response `200`: `{ "message": "Password updated" }`.
`400` with `Invalid or expired token` when the token is unknown, already used or expired,
and `400` with `Password must be at least 8 characters` for a short password. This route
never answers `401` — that status is reserved for expired sessions.

#### `POST /api/v1/auth/change-password`

Requires a bearer JWT. Rate-limited to **10 req/min per IP**. Lets the signed-in user
change their own password; the account is taken from the token, so a `username` in the
body is ignored and the login can never be changed here.

```bash
curl -X POST http://localhost:5000/api/v1/auth/change-password \
  -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' \
  -d '{"current_password":"atual","new_password":"nova-senha-forte"}'
```

Response `200`: `{ "message": "Password updated" }`.
`400` with `Current password is incorrect` when the current password does not match.

Password changes are written to the audit log as `PASSWORD_RESET` (via e-mail link) and
`PASSWORD_CHANGE` (self-service while signed in). Unlike `LOGIN`, they are listed by
default in `GET /api/v1/audit-logs`.

---

### Users — `can_manage_users`

| Method | Path                            | Description                                |
|--------|---------------------------------|--------------------------------------------|
| GET    | `/api/v1/users`                 | List all users                             |
| POST   | `/api/v1/users`                 | Create user. Body: `{username, password, <flag>: bool, …}` |
| PUT    | `/api/v1/users/<id>`            | Update username / password / any flag      |
| DELETE | `/api/v1/users/<id>`            | Delete user (cannot delete the last admin) |

Creating with a duplicate username returns `409`.

---

### Tables

| Method | Path                                  | Permission           | Description                          |
|--------|---------------------------------------|----------------------|--------------------------------------|
| GET    | `/api/v1/tables`                      | logged in            | List user-visible tables and views   |
| GET    | `/api/v1/tables/<name>/schema`        | logged in            | Column names and types               |
| PUT    | `/api/v1/tables/<name>`               | `can_manage_views`   | Rename. Body: `{new_name}`           |
| DELETE | `/api/v1/tables/<name>`               | `can_manage_views`   | Drop the table or view               |
| POST   | `/api/v1/tables/<name>/data`          | `can_upload`         | Insert one row. Body: `{data: {col: val, …}}` |

System tables (`_system_*`, `audit_log`) are filtered out of the listing.

---

### Query — `can_query`

#### `POST /api/v1/query`

Read-only SQL. Anything other than a single `SELECT` (validated by `validate_readonly_sql`) is rejected with `403`.

```bash
curl -X POST http://localhost:5000/api/v1/query \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT * FROM minha_tabela LIMIT 10"}'
```

Response: `{ "results": [ { ... }, ... ] }`.

---

### Reports

Saved SQL queries.

| Method | Path                                  | Permission           | Description                  |
|--------|---------------------------------------|----------------------|------------------------------|
| GET    | `/api/v1/reports`                     | logged in            | List reports                 |
| POST   | `/api/v1/reports`                     | `can_manage_views`   | Create. Body: `{name, description?, sql_query}` |
| PUT    | `/api/v1/reports/<id>`                | `can_manage_views`   | Update                       |
| DELETE | `/api/v1/reports/<id>`                | `can_manage_views`   | Delete                       |
| GET    | `/api/v1/reports/<id>/execute`        | logged in            | Run the saved query, return `{results, report}` |

---

### Managed SQL Functions

Persisted PostgreSQL functions stored in `_system_functions`. Authoring is gated by `can_manage_functions`; any logged-in user can list them.

| Method | Path                                  | Permission                | Description |
|--------|---------------------------------------|---------------------------|-------------|
| GET    | `/api/v1/functions`                   | logged in                 | List catalog (body included only if `can_manage_functions`) |
| GET    | `/api/v1/functions/<id>`              | `can_manage_functions`    | Single function with body |
| POST   | `/api/v1/functions/validate`          | `can_manage_functions`    | Lint a draft definition |
| POST   | `/api/v1/functions`                   | `can_manage_functions`    | Create |
| PUT    | `/api/v1/functions/<id>`              | `can_manage_functions`    | Update |
| DELETE | `/api/v1/functions/<id>`              | `can_manage_functions`    | Delete |

Create body:
```json
{
  "name": "Dobrar Valor",
  "kind": "scalar",
  "parameters": [{ "name": "valor", "type": "numeric" }],
  "return_type": "numeric",
  "sql_body": "SELECT valor * 2"
}
```

Functions are exposed as `fn_<slug>(...)` for use in `SELECT` queries.

---

### Views — `can_manage_views`

#### `PUT /api/v1/views/<view_name>`

Smart update of a view, including dependency reattachment. Optionally renames it.

```json
{ "definition": "SELECT ... FROM ...", "new_name": "optional_new_name" }
```

---

### Files & Uploads

| Method | Path                          | Permission       | Description                                    |
|--------|-------------------------------|------------------|------------------------------------------------|
| POST   | `/api/v1/map-file`            | `can_upload`     | Multipart `file=<xlsx/csv>`. Returns inferred schema. |
| POST   | `/api/v1/upload`              | `can_upload`     | Multipart `file=…` plus `table_name` form field. Imports rows. |

Max body size: 100 MB.

---

### Audit Log — `can_view_audit`

#### `GET /api/v1/audit-logs`

Paginated, filtered list.

Query params:

| Param         | Type        | Description |
|---------------|-------------|-------------|
| `page`        | int         | 1-indexed, default 1 |
| `page_size`   | int         | default 25 |
| `entity_type` | string      | `user`, `report`, `view`, `table`, `table_row`, `file`, `session`, `function` |
| `action`      | string      | `CREATE`, `UPDATE`, `DELETE`, `UPLOAD`, `RENAME`, `LOGIN`, `ANALYZE`, `QUERY` |
| `user_id`     | int         | filter by acting user |
| `from`, `to`  | ISO 8601    | timestamp range |
| `q`           | string      | free-text search across `entity_id` / `username` |

Response:
```json
{
  "logs": [{ "id": 42, "ts": "2026-04-27T22:00:00Z", "username": "admin",
             "action": "UPDATE", "entity_type": "report", "entity_id": "7",
             "status": "success" }],
  "total": 137, "page": 1, "page_size": 25
}
```

#### `GET /api/v1/audit-logs/<id>`

Single entry with `before_state`, `after_state`, `metadata`, `error`. Sensitive fields (`password`, `password_hash`, `token`, `secret`) are redacted before persistence; oversized JSON bodies (>64 KB) are truncated.

---

## Endpoint inventory

Summary with permission gates (the complete, verified list of routes and destinations is `datarepo-web/tests/routes.tsv`):

<!-- AUTO-GENERATED:ENDPOINTS -->
- `POST   /api/v1/auth/login` (rate-limited 10/min)
- `GET    /api/v1/auth/me`
- `POST   /api/v1/auth/forgot-password` (public, rate-limited 5/min)
- `POST   /api/v1/auth/reset-password` (public, rate-limited 10/min)
- `POST   /api/v1/auth/change-password` (login, rate-limited 10/min)
- `GET    /api/v1/users`                              · `can_manage_users`
- `POST   /api/v1/users`                              · `can_manage_users`
- `PUT    /api/v1/users/<id>`                         · `can_manage_users`
- `DELETE /api/v1/users/<id>`                         · `can_manage_users`
- `POST   /api/v1/map-file`                           · `can_upload`
- `POST   /api/v1/upload`                             · `can_upload`
- `GET    /api/v1/tables`                             · login
- `GET    /api/v1/tables/<name>/schema`               · login
- `PUT    /api/v1/tables/<name>`                      · `can_manage_views`
- `DELETE /api/v1/tables/<name>`                      · `can_manage_views`
- `POST   /api/v1/tables/<name>/data`                 · `can_upload`
- `POST   /api/v1/query`                              · `can_query`
- `GET    /api/v1/reports`                            · login
- `POST   /api/v1/reports`                            · `can_manage_views`
- `PUT    /api/v1/reports/<id>`                       · `can_manage_views`
- `DELETE /api/v1/reports/<id>`                       · `can_manage_views`
- `GET    /api/v1/reports/<id>/execute`               · login
- `GET    /api/v1/functions`                          · login
- `GET    /api/v1/functions/<id>`                     · `can_manage_functions`
- `POST   /api/v1/functions/validate`                 · `can_manage_functions`
- `POST   /api/v1/functions`                          · `can_manage_functions`
- `PUT    /api/v1/functions/<id>`                     · `can_manage_functions`
- `DELETE /api/v1/functions/<id>`                     · `can_manage_functions`
- `PUT    /api/v1/views/<name>`                       · `can_manage_views`
- `GET    /api/v1/audit-logs`                         · `can_view_audit`
- `GET    /api/v1/audit-logs/<id>`                    · `can_view_audit`
<!-- /AUTO-GENERATED:ENDPOINTS -->
