"""Regra de nome de objeto de dados do usuario (tabela, view, view materializada).

Compartilhada por `ingestion` (que cria tabelas) e api (que renomeia,
apaga e redefine views). Nomes chegam a DDL por interpolacao, entao esta
validacao e a barreira contra injecao — as duas pontas precisam da MESMA regra,
por isso ela mora no kit e nao em copias soltas.
"""
import re

DATA_OBJECT_NAME_RE = re.compile(r'^[a-z][a-z0-9_]*$')
SYSTEM_DATA_OBJECTS = {'reports', 'audit_log'}


def validate_data_object_name(name):
    if not name or not DATA_OBJECT_NAME_RE.fullmatch(name):
        raise ValueError(
            "Name must start with a lowercase letter and contain only "
            "lowercase letters, numbers, and underscores."
        )
    if name.startswith('_') or name in SYSTEM_DATA_OBJECTS:
        raise ValueError("System objects cannot be changed.")
    return name


def quote_identifier(name):
    return f'"{validate_data_object_name(name)}"'
