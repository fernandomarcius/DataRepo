"""schema inicial: tabelas de sistema do monolito

Linha de base. Reproduz, sem mudar nada, o DDL que o monolito executava a cada
boot nas funcoes init_*_table(). Por ser todo IF NOT EXISTS, aplicar esta
migration no banco de producao que ja existe NAO altera nada: so registra a
versao em `_alembic_version`. Num banco vazio, cria o schema completo.

As extensoes ficam em blocos tolerantes: a ausencia de pg_cron ou tds_fdw
desliga a funcionalidade correspondente (o api avisa no log ao subir), mas nao
impede o resto do schema de existir. Instalar extensao exige superusuario; o
que o banco precisa esta em docs/database/.

Revision ID: 0001
Revises:
Create Date: 2026-09-25
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _extensao_opcional(nome, para_que):
    op.execute(f"""
    DO $$
    BEGIN
        CREATE EXTENSION IF NOT EXISTS {nome};
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'extensao {nome} indisponivel ({para_que}): %', SQLERRM;
    END
    $$;
    """)


def upgrade():
    # --- extensoes -----------------------------------------------------------
    _extensao_opcional("tds_fdw", "conexoes com SQL Server")
    _extensao_opcional("postgres_fdw", "conexoes com Postgres externo")
    # pg_cron so pode ser criado no banco de cron.database_name e com
    # shared_preload_libraries=pg_cron; senao o refresh agendado fica desligado.
    _extensao_opcional("pg_cron", "refresh agendado de views materializadas")

    # --- usuarios e autenticacao --------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS _system_users (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        can_query BOOLEAN NOT NULL DEFAULT FALSE,
        can_upload BOOLEAN NOT NULL DEFAULT FALSE,
        can_manage_views BOOLEAN NOT NULL DEFAULT FALSE,
        can_manage_functions BOOLEAN NOT NULL DEFAULT FALSE,
        can_manage_users BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ALTER TABLE _system_users ADD COLUMN IF NOT EXISTS can_manage_functions BOOLEAN NOT NULL DEFAULT FALSE;
    ALTER TABLE _system_users ADD COLUMN IF NOT EXISTS can_view_audit BOOLEAN NOT NULL DEFAULT FALSE;
    ALTER TABLE _system_users ADD COLUMN IF NOT EXISTS can_manage_connections BOOLEAN NOT NULL DEFAULT FALSE;
    -- Backfill que o monolito repetia a cada boot: admins recebem as flags que
    -- surgiram depois deles. Idempotente.
    UPDATE _system_users
    SET can_manage_functions = TRUE
    WHERE can_manage_users = TRUE AND can_manage_functions = FALSE;
    UPDATE _system_users
    SET can_manage_connections = TRUE
    WHERE can_manage_users = TRUE AND can_manage_connections = FALSE;
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS _system_password_resets (
        id          BIGSERIAL PRIMARY KEY,
        user_id     INT NOT NULL REFERENCES _system_users(id) ON DELETE CASCADE,
        token_hash  TEXT NOT NULL UNIQUE,
        expires_at  TIMESTAMPTZ NOT NULL,
        used_at     TIMESTAMPTZ,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        ip          TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_password_resets_user ON _system_password_resets (user_id);
    """)

    # --- auditoria ------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id           BIGSERIAL PRIMARY KEY,
        ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
        user_id      INT REFERENCES _system_users(id) ON DELETE SET NULL,
        username     TEXT,
        action       TEXT NOT NULL,
        entity_type  TEXT NOT NULL,
        entity_id    TEXT,
        before_state JSONB,
        after_state  JSONB,
        metadata     JSONB,
        status       TEXT NOT NULL DEFAULT 'success',
        error        TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_audit_log_ts     ON audit_log (ts DESC);
    CREATE INDEX IF NOT EXISTS idx_audit_log_user   ON audit_log (user_id);
    CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log (entity_type, entity_id);
    CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log (action);
    """)

    # --- relatorios, views e materializacoes ---------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS _system_reports (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        sql_query TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_report_name UNIQUE (name)
    );

    CREATE TABLE IF NOT EXISTS _system_materialized_views (
        view_name         TEXT PRIMARY KEY,
        report_id         INTEGER REFERENCES _system_reports(id) ON DELETE CASCADE,
        refresh_cron      TEXT NOT NULL,
        preset            JSONB NOT NULL,
        cron_jobid        BIGINT,
        cron_jobname      TEXT,
        last_refreshed_at TIMESTAMP,
        last_status       TEXT,
        last_error        TEXT,
        created_by        TEXT,
        created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS _view_history (
        id SERIAL PRIMARY KEY,
        view_name TEXT NOT NULL,
        view_definition TEXT NOT NULL,
        operation TEXT NOT NULL,
        related_to TEXT,
        dropped_at TIMESTAMP DEFAULT NOW()
    );
    """)

    # --- funcoes gerenciadas --------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS _system_functions (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        function_name TEXT NOT NULL UNIQUE,
        description TEXT,
        kind TEXT NOT NULL CHECK (kind IN ('scalar', 'table')),
        parameters JSONB NOT NULL DEFAULT '[]'::jsonb,
        return_type TEXT,
        return_columns JSONB NOT NULL DEFAULT '[]'::jsonb,
        sql_body TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # --- conexoes externas (FDW) ----------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS _system_connections (
        id              SERIAL PRIMARY KEY,
        name            TEXT NOT NULL UNIQUE,
        display_name    TEXT NOT NULL,
        db_type         TEXT NOT NULL CHECK (db_type IN ('sqlserver','postgres')),
        host            TEXT NOT NULL,
        port            INTEGER NOT NULL,
        database        TEXT NOT NULL,
        remote_schema   TEXT,
        username        TEXT NOT NULL,
        password_enc    TEXT NOT NULL,
        options         JSONB NOT NULL DEFAULT '{}'::jsonb,
        last_synced_at  TIMESTAMPTZ,
        created_at      TIMESTAMPTZ DEFAULT now(),
        updated_at      TIMESTAMPTZ DEFAULT now()
    );
    """)

    # --- aliases de coluna (escritos pelo ingestion, lidos pelo api) ----------
    op.execute("""
    CREATE TABLE IF NOT EXISTS _column_aliases (
        id SERIAL PRIMARY KEY,
        table_name TEXT NOT NULL,
        physical_column TEXT NOT NULL,
        alias TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(table_name, alias),
        UNIQUE(table_name, physical_column)
    );
    """)


def downgrade():
    # Linha de base: desfazer apagaria os dados de producao. Para voltar, restaure
    # um backup.
    raise RuntimeError("a migration inicial nao tem downgrade")
