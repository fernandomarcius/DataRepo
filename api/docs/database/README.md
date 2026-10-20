# Banco de dados

O DataRepo **não sobe nem gerencia o Postgres**: api, api-query e ingestion
se conectam a um banco existente por `DATABASE_URL`. O schema das tabelas de
sistema vem das migrations (`migrations/`, Alembic), aplicadas pelo deploy do api.

`Dockerfile.example` é a referência do que esse banco precisa ter. Também é a
imagem usada pelo ambiente de desenvolvimento (`deploy/docker-compose.dev.yml`) e
pelos testes de migration (`tools/check-migrations.sh`).

## Requisitos

| Requisito | Para quê | Sem ele |
|---|---|---|
| PostgreSQL 15+ (produção: 18) | — | — |
| `pg_cron`, com `shared_preload_libraries=pg_cron` e `cron.database_name` = banco da aplicação | refresh agendado de views materializadas | materializar funciona, sem agendamento |
| `tds_fdw` | conexões com SQL Server | conexões SQL Server falham |
| `postgres_fdw` (contrib) | conexões com Postgres externo | conexões Postgres falham |
| `timezone = America/Sao_Paulo` (e `cron.timezone`) | datas de registro e agenda do pg_cron | horários deslocados |

A migration `0001` tenta criar as três extensões e, se não conseguir, só avisa.
O api loga `WARN: extensao ... ausente` a cada boot enquanto faltar alguma.

## Permissões do usuário da aplicação

O mesmo usuário (o de `DATABASE_URL`) roda as migrations e a aplicação. Ele
precisa criar e alterar tabelas, views, views materializadas, funções, schemas
(`ext_*`), `SERVER` e `USER MAPPING` no banco, e usar o schema `cron`.

`CREATE EXTENSION` exige superusuário: se o usuário da aplicação não for, crie
as extensões antes, como superusuário:

```sql
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS tds_fdw;
CREATE EXTENSION IF NOT EXISTS postgres_fdw;
```

