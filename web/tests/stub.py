"""Servicos-stub para o teste de roteamento: cada porta responde com o nome do
servico que representa, o caminho recebido e o X-Forwarded-For que chegou."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVICOS = {5001: "api", 5002: "query", 5003: "ingestion"}


def handler_para(nome):
    class Handler(BaseHTTPRequestHandler):
        def _responder(self):
            corpo = json.dumps({
                "service": nome,
                "path": self.path,
                "xff": self.headers.get("X-Forwarded-For"),
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        do_GET = do_POST = do_PUT = do_DELETE = _responder

        def log_message(self, *args):
            pass

    return Handler


if __name__ == "__main__":
    servidores = [ThreadingHTTPServer(("0.0.0.0", porta), handler_para(nome)) for porta, nome in SERVICOS.items()]
    for s in servidores[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    print("stubs prontos", flush=True)
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    servidores[0].serve_forever()
