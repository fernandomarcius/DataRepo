"""Envio de eventos de auditoria para o api, a partir de outro processo.

Usado pelo `ingestion`. (O proprio api grava os seus eventos na requisicao, por
services.audit_service.log_event, e usa daqui so `build_event`.)

Mesma garantia do monolito: log_event() NUNCA levanta excecao, porque auditoria
nao pode derrubar a operacao de negocio.

O evento e montado no thread da requisicao (onde `g.current_user`, IP e
User-Agent existem), redigido, e posto numa fila em memoria; um thread de fundo
por processo entrega ao api via POST /internal/v1/events. A resposta ao usuario
nao espera o api, e o api fora do ar nao vira latencia nem erro no upload.

O custo, registrado no ADR 0004: se o api estiver indisponivel alem das
tentativas, o evento nao e persistido. Ele e escrito INTEIRO (ja redigido) no
stderr com o prefixo `AUDIT_UNDELIVERED`, de onde pode ser reprocessado a partir
dos logs do container.
"""
import atexit
import json
import os
import queue
import sys
import threading
import time
from typing import Any, Optional

from kit.internal import InternalCallError, call_json, service_url
from kit.serialization import convert_to_serializable

# Flask globals — acessados por funcao para os testes poderem trocar.
try:
    import flask as _flask

    def _get_flask_g():  # pragma: no cover
        return _flask.g

    def _get_flask_request():  # pragma: no cover
        return _flask.request

except ImportError:  # pragma: no cover
    def _get_flask_g():
        return None

    def _get_flask_request():
        return None


_SENSITIVE_KEYS = {"password", "password_hash", "token", "secret"}

QUEUE_MAX = 1000
SEND_ATTEMPTS = 3
SHUTDOWN_FLUSH_SECONDS = 5


def redact(obj: Any) -> Any:
    """Remove recursivamente chaves sensiveis de dicts/listas."""
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if str(k).lower() in _SENSITIVE_KEYS else redact(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact(item) for item in obj]
    return obj


def _jsonable(value: Any) -> Any:
    """Garante que o valor atravessa a rede: tipos do Postgres viram texto."""
    if value is None:
        return None
    return json.loads(json.dumps(convert_to_serializable(value), default=str))


def _current_user():
    try:
        flask_g = _get_flask_g()
        current_user = getattr(flask_g, "current_user", None) if flask_g is not None else None
        if not isinstance(current_user, dict) and hasattr(flask_g, "get"):
            current_user = flask_g.get("current_user")
        if isinstance(current_user, dict):
            return current_user.get("id"), current_user.get("username")
    except RuntimeError:
        pass  # fora de contexto de requisicao
    return None, None


def _request_meta() -> dict:
    meta = {}
    try:
        flask_req = _get_flask_request()
        if flask_req is not None:
            ip = getattr(flask_req, "remote_addr", None)
            user_agent = getattr(flask_req, "headers", {}).get("User-Agent")
            if isinstance(ip, str):
                meta["ip"] = ip
            if isinstance(user_agent, str):
                meta["user_agent"] = user_agent
    except RuntimeError:
        pass
    return meta


def build_event(
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    *,
    before: Any = None,
    after: Any = None,
    status: str = "success",
    error: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    user_id, username = _current_user()
    enriched_meta = dict(metadata or {})
    for key, value in _request_meta().items():
        enriched_meta.setdefault(key, value)
    return {
        "user_id": user_id,
        "username": username,
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id is not None else None,
        "before": redact(_jsonable(before)),
        "after": redact(_jsonable(after)),
        "metadata": redact(_jsonable(enriched_meta)) if enriched_meta else None,
        "status": status,
        "error": error,
        "source": os.getenv("SERVICE_NAME"),
    }


class _Dispatcher:
    """Fila + thread de entrega, recriados apos fork (gunicorn forka workers)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._pid = None
        self._queue = None
        self._thread = None

    def _ensure_started(self):
        if self._pid == os.getpid() and self._thread is not None and self._thread.is_alive():
            return
        with self._lock:
            if self._pid == os.getpid() and self._thread is not None and self._thread.is_alive():
                return
            self._pid = os.getpid()
            self._queue = queue.Queue(maxsize=QUEUE_MAX)
            self._thread = threading.Thread(target=self._run, name="audit-dispatcher", daemon=True)
            self._thread.start()

    def submit(self, event: dict) -> None:
        self._ensure_started()
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            _undelivered(event, "fila local cheia")

    def _run(self):
        q = self._queue
        while True:
            event = q.get()
            try:
                send_event(event)
            finally:
                q.task_done()

    def flush(self, timeout: float) -> None:
        q = self._queue
        if q is None or self._pid != os.getpid():
            return
        deadline = time.monotonic() + timeout
        while q.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.05)


_dispatcher = _Dispatcher()


def _undelivered(event: dict, reason: str) -> None:
    print(
        f"AUDIT_UNDELIVERED ({reason}): "
        + json.dumps(event, separators=(",", ":"), ensure_ascii=False, default=str),
        file=sys.stderr,
        flush=True,
    )


def send_event(event: dict) -> None:
    """Entrega sincrona com poucas tentativas. Nunca levanta."""
    url = service_url("AUDIT_SERVICE_URL", "http://api:5000") + "/internal/v1/events"
    last_error = None
    for attempt in range(SEND_ATTEMPTS):
        try:
            call_json("POST", url, event)
            return
        except (InternalCallError, RuntimeError) as e:
            last_error = e
            time.sleep(0.2 * (2 ** attempt))
        except Exception as e:  # pragma: no cover -- rede nunca pode derrubar o dispatcher
            last_error = e
            break
    _undelivered(event, str(last_error))


def log_event(
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    *,
    before: Any = None,
    after: Any = None,
    status: str = "success",
    error: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Registra um evento de auditoria. NUNCA levanta excecao."""
    try:
        event = build_event(
            action, entity_type, entity_id,
            before=before, after=after, status=status, error=error, metadata=metadata,
        )
        _dispatcher.submit(event)
    except Exception as exc:
        print(f"AUDIT ERROR: {exc}", file=sys.stderr, flush=True)


@atexit.register
def _flush_on_exit():  # pragma: no cover
    _dispatcher.flush(SHUTDOWN_FLUSH_SECONDS)
