"""api — o backend do DataRepo, exceto upload/parsing (servico `ingestion`).

Um app Flask com um blueprint por dominio: autenticacao/usuarios, auditoria,
catalogo (tabelas, views, relatorios, materializacoes), consulta, funcoes e
conexoes externas. O schema do banco e versionado em migrations/ (Alembic) e
aplicado pelo deploy ANTES de o app subir; o boot nao cria tabelas.

A mesma imagem roda em dois containers: `api` (tudo) e `api-query`, para onde o
nginx do web manda so /api/v1/query — consulta longa nao ocupa os workers do login.
O `api-query` sobe com RUN_STARTUP_TASKS=0.
"""
import os

from db import execute_query
from kit.web import create_app, init_step
from routes import audit, catalog, connections, functions, identity, query
from routes.identity import limiter
from services.auth_service import seed_admin_user
from services.materialized_view_service import reconcile_on_startup
from services.password_reset_service import purge_expired_resets

app = create_app(__name__)
limiter.init_app(app)

for blueprint in (identity.bp, audit.bp, catalog.bp, query.bp, functions.bp, connections.bp):
    app.register_blueprint(blueprint)

# Extensoes que o banco precisa ter (ver docs/database/). Faltar uma nao impede o
# boot — so desliga a funcionalidade que depende dela — mas precisa aparecer no log.
REQUIRED_EXTENSIONS = {
    "pg_cron": "refresh agendado de views materializadas",
    "tds_fdw": "conexoes com SQL Server",
    "postgres_fdw": "conexoes com Postgres externo",
}


def check_database_extensions():
    rows = execute_query(
        "SELECT extname FROM pg_extension WHERE extname IN ('pg_cron', 'tds_fdw', 'postgres_fdw')"
    ) or []
    present = {r["extname"] for r in rows}
    for ext, feature in REQUIRED_EXTENSIONS.items():
        if ext not in present:
            print(f"WARN: extensao {ext} ausente no banco — {feature} indisponivel", flush=True)


if os.getenv("RUN_STARTUP_TASKS", "1") == "1":
    # Tarefas de DADOS, nao de schema: as tabelas ja existem (migrations).
    init_step("seed admin user", seed_admin_user)
    init_step("purge expired password resets", purge_expired_resets)
    # Reconcilia builds/refreshes de views materializadas interrompidos por restart.
    init_step("reconcile materialized views", reconcile_on_startup)
    init_step("check database extensions", check_database_extensions)


if __name__ == '__main__':
    # Caminho de desenvolvimento local apenas. Em producao a imagem sobe via
    # gunicorn (ver Dockerfile): `debug=True` expoe o console interativo do
    # Werkzeug, que e execucao remota de codigo para quem alcancar a porta.
    # nosemgrep: avoid_app_run_with_bad_host -- caminho de dev local apenas; producao usa gunicorn
    app.run(host='0.0.0.0', port=5000, debug=os.getenv('FLASK_DEBUG') == '1')
