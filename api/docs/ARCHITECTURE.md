# Arquitetura

Aplicação interna de repositório de dados: upload de planilhas/PDF para tabelas,
consultas SQL read-only, relatórios salvos (views) e materializados, funções SQL
gerenciadas, conexões com bancos externos via FDW, usuários com permissões por
flag e trilha de auditoria universal. Decisão e trade-offs: ADR 0004.

## Workloads

```
Navegador ──► web (nginx, :5173 e :5000)
                 ├── /  (SPA React, arquivos estáticos)
                 ├── /api/v1/query                         → api-query  (mesma imagem do api)
                 ├── /api/v1/upload, /map-file,
                 │   /inspect-headers, /tables/<t>/data    → ingestion  (pandas, camelot, OpenCV)
                 ├── /api/v1/*  (todo o resto)             → api
                 └── /internal/*                           → 404

ingestion ──► api   POST /internal/v1/events   (eventos de auditoria; fila + 3 tentativas)
api, api-query, ingestion ──► Postgres existente (DATABASE_URL)
```

### api (este repositório)

Um app Flask (`app.py`) com um blueprint por domínio em `routes/` e a lógica em
`services/`:

| Blueprint | Rotas | Serviços |
|---|---|---|
| `identity` | `/auth/*`, `/users*` | `auth_service`, `password_reset_service`, `email_service` |
| `audit` | `/audit-logs*`, `/internal/v1/events` | `audit_service` |
| `catalog` | `/tables*` (exceto `POST .../data`), `/views/*`, `/reports*` | `data_object_service`, `view_service`, `report_service`, `materialized_view_service` |
| `query` | `/query` | `db.execute_readonly_query` |
| `functions` | `/functions*` | `function_service` |
| `connections` | `/connections*` | `connection_service` |

No boot, só tarefas de dados (seed do admin, limpeza de tokens de senha,
reconciliação de materializações, aviso de extensões ausentes), desligadas no
`api-query` (`RUN_STARTUP_TASKS=0`). O schema vem de `migrations/`.

## Preocupações transversais

| Preocupação | Mecanismo | Onde |
|---|---|---|
| Autenticação | JWT HS256, 12 h; emitido só pelo api | `services/auth_service.py` |
| Autorização | flags no payload do JWT, verificadas localmente | `kit/auth.py` |
| Auditoria | api: INSERT na requisição; ingestion: evento → `/internal/v1/events` | `services/audit_service.py`, `kit/audit_client.py` |
| Chamada interna | `X-Internal-Token` + nginx bloqueia `/internal` | `kit/internal.py` |
| IP do cliente | nginx sobrescreve `X-Forwarded-For`; serviços confiam em 1 salto | template do web, `kit/web.py` |
| Rate limit | `flask-limiter`, login 10/min/IP | `routes/identity.py` |
| SQL read-only | guarda por palavra-chave + transação `READ ONLY` | `kit/sql_guard.py`, `db.execute_readonly_query` |
| Nome de objeto | regex única contra injeção em DDL | `kit/identifiers.py` |
| Schema | Alembic, migrations à mão, aplicadas no deploy | `migrations/` |
| Saúde | `/healthz` + `HEALTHCHECK` em toda imagem | `kit/web.py`, Dockerfiles |

