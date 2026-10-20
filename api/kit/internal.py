"""Chamadas servico-a-servico.

Rotas `/internal/...` nunca sao publicadas pelo nginx de borda do web (ele responde 404 para
esse prefixo) e, alem disso, exigem o header `X-Internal-Token` igual a
`INTERNAL_API_TOKEN`. As duas barreiras sao independentes de proposito: um
servico exposto por engano numa porta do host continua sem aceitar evento de
auditoria forjado.
"""
import hmac
import json
import os
import urllib.error
import urllib.request
from functools import wraps

from flask import jsonify, request

INTERNAL_TOKEN_HEADER = "X-Internal-Token"
DEFAULT_TIMEOUT_SECONDS = 3


def internal_token() -> str:
    token = os.getenv("INTERNAL_API_TOKEN")
    if not token:
        raise RuntimeError("INTERNAL_API_TOKEN environment variable is required")
    return token


def internal_only(fn):
    """Aceita a requisicao so com o token interno correto (comparacao constante)."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        expected = os.getenv("INTERNAL_API_TOKEN")
        received = request.headers.get(INTERNAL_TOKEN_HEADER, "")
        # Sem token configurado o endpoint fica fechado, nunca aberto.
        if not expected or not hmac.compare_digest(received.encode(), expected.encode()):
            return jsonify({"error": "Forbidden"}), 403
        return fn(*args, **kwargs)

    return wrapper


def service_url(env_var: str, default: str) -> str:
    return (os.getenv(env_var) or default).rstrip("/")


class InternalCallError(Exception):
    """Falha ao falar com outro servico (rede, timeout ou status >= 400)."""


def call_json(method: str, url: str, payload=None, timeout: float = DEFAULT_TIMEOUT_SECONDS):
    """Faz uma chamada interna e devolve o JSON da resposta.

    stdlib de proposito: evita trazer `requests` para quem so precisa
    disto, e o contrato aqui e simples (JSON in, JSON out).
    """
    data = None
    headers = {INTERNAL_TOKEN_HEADER: internal_token(), "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        # nosemgrep: dynamic-urllib-use-detected -- URL vem de configuracao do servico, nunca do usuario
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        raise InternalCallError(f"{method} {url} -> HTTP {e.code}") from e
    except (urllib.error.URLError, OSError) as e:
        raise InternalCallError(f"{method} {url} -> {e}") from e
    return json.loads(body) if body else None
