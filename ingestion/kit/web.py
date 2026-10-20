"""Fabrica do app Flask: o que todo servico precisa igual.

- CORS e `sort_keys=False`, como no monolito;
- ProxyFix com UM salto confiavel: o unico caminho ate api e ingestion e o nginx do web,
  que preenche X-Forwarded-For. Sem isso `request.remote_addr` seria o IP do
  nginx, e o rate limit por IP do login viraria um limite global compartilhado
  por todos os usuarios (que era o comportamento do monolito atras do nginx);
- `/healthz` para o HEALTHCHECK da imagem e para o deploy esperar o container.
"""
import os
import time

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix


def create_app(import_name: str) -> Flask:
    app = Flask(import_name)
    CORS(app)
    app.json.sort_keys = False
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

    service = os.getenv("SERVICE_NAME", import_name)

    @app.route("/healthz", methods=["GET"])
    def healthz():
        return jsonify({"status": "ok", "service": service}), 200

    return app


def init_step(label, fn, attempts=3, delay_seconds=1.0):
    """Roda um passo idempotente de inicializacao sem derrubar o boot.

    Mesmo contrato do monolito: Postgres ainda subindo nao impede o processo de
    iniciar; o passo e refeito no proximo restart.

    As tentativas extras cobrem a corrida entre os workers do gunicorn, que
    importam o app ao mesmo tempo: dois `CREATE TABLE IF NOT EXISTS`
    simultaneos fazem um deles falhar com UniqueViolation em pg_type, e a
    segunda tentativa ja encontra a tabela criada.
    """
    for attempt in range(1, attempts + 1):
        try:
            fn()
            return True
        except Exception as e:
            if attempt == attempts:
                print(f"Failed to {label}: {e}", flush=True)
                return False
            time.sleep(delay_seconds)
