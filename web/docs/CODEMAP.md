<!-- Generated: 2026-04-28 | Files scanned: 21 | Token estimate: ~750 -->

# Frontend

Vite + React 18 SPA, Tailwind CSS, react-router v7, axios. Built bundle is served by nginx in the production image.

## Route tree (`src/App.jsx`)

```
ThemeProvider
└── Router
    └── AuthProvider
        ├── /login              → <Login>
        └── RequireAuth → Shell (Navbar + <Outlet>)
            ├── /            (can_query → /reports)  → <QueryInterface>
            ├── /reports                              → <ReportsPage>
            ├── /functions   (can_manage_functions)   → <FunctionsPage>
            ├── /upload      (can_upload)             → <UploadSection>
            ├── /users       (can_manage_users)       → <UsersPage>
            ├── /audit       (can_view_audit)         → <AuditLogPage>
            └── *            → <Navigate to="/">
```

`<RequirePermission flag>` redirects to `redirectTo` (default `/`) if the flag is missing on `g.current_user.perms`.

## Component inventory

```
src/
├── App.jsx                            Router (basename = prefixo()) + providers
├── prefixo.js                         mount prefix from the bundle URL, import.meta.url ('' at the root)
├── main.jsx                           ReactDOM.render
├── index.css                          Tailwind directives
├── api/
│   └── client.js                      axios instance, /api/v1, JWT interceptor, 401 → logout event
├── auth/
│   ├── RequireAuth.jsx                gate: redirect to /login if no user
│   └── RequirePermission.jsx          gate: redirect if perm flag missing
├── context/
│   ├── AuthContext.jsx                user state, login/logout, token persistence (localStorage)
│   └── ThemeContext.jsx               light/dark toggle, persisted
├── components/
│   ├── Navbar.jsx                     top nav, links gated by perms, theme toggle
│   ├── Login.jsx                      POST /auth/login form
│   ├── QueryInterface.jsx             SQL editor + ResultsTable (uses VisualQueryBuilder, SchemaBrowser)
│   ├── VisualQueryBuilder.jsx         drag/drop column picker
│   ├── SchemaBrowser.jsx              left rail showing tables/views/columns
│   ├── ResultsTable.jsx               paginated table renderer
│   ├── UploadSection.jsx              Excel/CSV upload, preview via /map-file, commit via /upload
│   ├── DataEntryForm.jsx              row append form for an existing table
│   ├── ReportsPage.jsx                list/create/edit/run saved reports
│   ├── FunctionsPage.jsx              managed SQL functions CRUD
│   ├── UsersPage.jsx                  user CRUD + permission flag toggles
│   ├── AuditLogPage.jsx               filtered/paginated audit list
│   ├── AuditLogDetail.jsx             modal: side-by-side diff (react-diff-viewer-continued)
│   └── ErrorBoundary.jsx              catches render errors below it
└── utils/
    └── auditFormat.js                 action label/badge color, JSON pretty
```

## State

- **Auth**: `AuthContext` holds `{user, loading}`. `login()` writes token to `localStorage` and refetches `/auth/me`. `logout()` clears storage. The axios response interceptor dispatches `auth:unauthorized` on any 401 — `AuthProvider` listens and clears state.
- **Theme**: `ThemeContext` toggles a `dark` class on `<html>`, persisted in `localStorage`.
- **Per-page**: components use `useState` + `useEffect`. No Redux / React Query — all server state is fetched ad hoc via the `api` axios instance.

## API client (`api/client.js`)

- ``baseURL: `${prefixo()}/api/v1``` — `/api/v1` at the root of a host (dev via Vite proxy, prod via nginx); under a prefix (`/workloads/{tenant}/{service}`, `/dataapp`) the prefix comes first (`src/prefixo.js`)
- Request interceptor: injects `Authorization: Bearer <token>` from `localStorage`
- Response interceptor: on 401, clears token + dispatches `auth:unauthorized`
- Audit-log helpers exported: `getAuditLogs(params)`, `getAuditLog(id)`. Other endpoints are called inline with `api.get/post/...` from each component.

## Build

| Command | Output |
|---------|--------|
| `npm run dev` | Vite dev server on 5173 |
| `npm run build` | `dist/` bundled assets |
| `npm run lint` | ESLint across `src/` |
| `npm run preview` | Serve built `dist/` locally |

Production image: `node:22-alpine` build stage → `dist/` copied into `nginx:alpine`. Dockerfile expects `frontend/nginx.conf` next to it (referenced but not in this map).
