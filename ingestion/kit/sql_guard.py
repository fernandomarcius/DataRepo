"""Guarda de SQL read-only do api: consultas, relatorios e corpo de funcoes.

Extraida sem mudanca de regra do antigo `function_service.validate_readonly_sql`.
A barreira real continua sendo a transacao READ ONLY de `db.execute_readonly_query`;
esta validacao existe para recusar cedo, com mensagem clara, e para impedir que
uma definicao de view ou funcao carregue DDL/DML.
"""
import re

FORBIDDEN_SQL_KEYWORDS = (
    "insert",
    "update",
    "delete",
    "drop",
    "truncate",
    "alter",
    "create",
    "grant",
    "revoke",
    "copy",
    "call",
    "do",
    "execute",
    "refresh",
    "vacuum",
    "reindex",
)


class ReadOnlySQLError(ValueError):
    """SQL recusado por nao ser uma unica instrucao SELECT/WITH sem DDL/DML."""


def mask_sql_literals(sql: str) -> str:
    masked = []
    i = 0
    length = len(sql)
    while i < length:
        ch = sql[i]

        if ch == "-" and i + 1 < length and sql[i + 1] == "-":
            end = sql.find("\n", i + 2)
            if end == -1:
                masked.append(" " * (length - i))
                break
            masked.append(" " * (end - i))
            i = end
            continue

        if ch == "/" and i + 1 < length and sql[i + 1] == "*":
            end = sql.find("*/", i + 2)
            if end == -1:
                masked.append(" " * (length - i))
                break
            masked.append(" " * (end + 2 - i))
            i = end + 2
            continue

        if ch == "'":
            start = i
            i += 1
            while i < length:
                if sql[i] == "'" and i + 1 < length and sql[i + 1] == "'":
                    i += 2
                    continue
                if sql[i] == "'":
                    i += 1
                    break
                i += 1
            masked.append(" " * (i - start))
            continue

        if ch == '"':
            start = i
            i += 1
            while i < length:
                if sql[i] == '"' and i + 1 < length and sql[i + 1] == '"':
                    i += 2
                    continue
                if sql[i] == '"':
                    i += 1
                    break
                i += 1
            masked.append(" " * (i - start))
            continue

        masked.append(ch)
        i += 1
    return "".join(masked)


def validate_readonly_sql(sql: str) -> str:
    if not isinstance(sql, str) or not sql.strip():
        raise ReadOnlySQLError("SQL obrigatório")

    clean = sql.strip()
    masked = mask_sql_literals(clean)
    stripped_masked = masked.strip()
    if not re.match(r"^(select|with)\b", stripped_masked, re.IGNORECASE):
        raise ReadOnlySQLError("A definição deve começar com SELECT ou WITH")

    internal_semicolons = stripped_masked.rstrip().rstrip(";")
    if ";" in internal_semicolons:
        raise ReadOnlySQLError("Apenas uma instrução SQL é permitida")

    for keyword in FORBIDDEN_SQL_KEYWORDS:
        if re.search(rf"\b{keyword}\b", masked, re.IGNORECASE):
            raise ReadOnlySQLError(f"Comando não permitido em consultas read-only: {keyword.upper()}")

    return clean.rstrip(";").strip()
