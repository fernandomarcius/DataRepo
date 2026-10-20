"""Fixtures comuns da suite do ingestion.

Nenhum teste fala com o api de verdade: todo evento de auditoria que um handler
emite cai em `audit_events` (ou `self.audit_events`), onde o teste pode
conferi-lo. Sem este desvio o thread de entrega tentaria resolver `api:5000` e
poluiria a saida dos testes.
"""
import os
import sys

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32chars!")
os.environ.setdefault("INTERNAL_API_TOKEN", "test-internal-token")

# Raiz do servico no sys.path, independente de onde o pytest foi chamado.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def audit_events(request, monkeypatch):
    """Eventos de auditoria emitidos no teste. Em unittest.TestCase: self.audit_events."""
    from kit import audit_client

    captured = []
    monkeypatch.setattr(audit_client._dispatcher, "submit", captured.append)
    if request.instance is not None:
        request.instance.audit_events = captured
    return captured
