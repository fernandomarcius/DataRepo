"""Ambiente do Alembic.

Sem autogenerate, de proposito: o banco tem tabelas, views e funcoes criadas em
tempo de execucao pelos usuarios (uploads, relatorios, funcoes gerenciadas). Um
diff automatico contra os modelos as trataria como "sobrando" e proporia apaga-las.
Toda migration e escrita a mao e mexe so nas tabelas de sistema.

A tabela de controle e `_alembic_version` (com `_`): assim ela fica fora da
listagem de tabelas do usuario, que esconde nomes com esse prefixo.
"""
import os

from alembic import context
from sqlalchemy import create_engine, pool

VERSION_TABLE = "_alembic_version"


def _url():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL e obrigatoria para rodar migrations")
    return url


def run_migrations_offline():
    context.configure(url=_url(), literal_binds=True, version_table=VERSION_TABLE)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            version_table=VERSION_TABLE,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
