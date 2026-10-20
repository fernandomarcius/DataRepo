# Tag fixa, nunca `latest` (Handbook §10).
FROM python:3.11-slim

WORKDIR /app

# Lock com hash (requirements.lock): a imagem instala exatamente as versoes
# auditadas no PR, e um pacote trocado no indice nao passa pelo --require-hashes.
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

# O usuario precisa EXISTIR antes do `USER`: sem esta linha o build passa e o
# container morre no `docker run`.
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY --chown=app:app . .

# Non-root: container comprometido rodando como root escala para o host.
USER app

ENV SERVICE_NAME=api \
    PYTHONUNBUFFERED=1

EXPOSE 5000

# stdlib, sem curl na imagem: o deploy espera este estado ficar `healthy`.
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=4)"]

# gunicorn, nao o servidor embutido do Flask. O timeout acompanha o
# proxy_read_timeout de 300s do nginx do web.
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "3", \
     "--timeout", "300", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--no-control-socket", \
     "app:app"]
