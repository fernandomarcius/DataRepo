"""Fixtures comuns da suite do api.

- `db` e substituido por um mock ANTES de qualquer import do projeto: nenhum
  teste fala com Postgres (os testes que precisam de um comportamento de banco
  fazem patch de `services.<modulo>.execute_query`).
- Todo evento de auditoria emitido por uma rota cai em `audit_events` (ou
  `self.audit_events` num unittest.TestCase), em vez de ir para o banco.
"""
import os
import sys
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32chars!")
os.environ.setdefault("INTERNAL_API_TOKEN", "test-internal-token")
os.environ.setdefault("ADMIN_USERNAME", "")
os.environ.setdefault("ADMIN_PASSWORD", "")

# Raiz do repositorio no sys.path, independente de onde o pytest foi chamado.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.modules.setdefault(
    "db",
    MagicMock(
        engine=MagicMock(),
        execute_query=MagicMock(return_value=[]),
        execute_readonly_query=MagicMock(return_value=[]),
        LOCAL_SCHEMA="public",
    ),
)


@pytest.fixture(autouse=True)
def audit_events(request, monkeypatch):
    """Eventos de auditoria emitidos no teste. Em unittest.TestCase: self.audit_events."""
    from services import audit_service

    captured = []
    monkeypatch.setattr(audit_service, "_persist", captured.append)
    if request.instance is not None:
        request.instance.audit_events = captured
    return captured
