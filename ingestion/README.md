# datarepo-ingestion

Upload e parsing de arquivos (Excel, CSV, PDF) para tabelas do DataRepo.
Parte do DataRepo: ver o repositório do api (DataRepo), ADR 0004.

Separado do api pelo perfil de carga: é o único workload com pandas, camelot,
OpenCV e ghostscript, picos de CPU/memória e uploads de até 100 MB.

## Rotas

Servidas pelo nginx do `datarepo-web` nos mesmos caminhos do monólito.

| Método | Rota | Permissão |
|---|---|---|
| POST | `/api/v1/map-file` | `can_upload` |
| POST | `/api/v1/inspect-headers` | `can_upload` |
| POST | `/api/v1/upload` | `can_upload` |
| POST | `/api/v1/tables/<table_name>/data` | `can_upload` |

`GET /healthz` responde sem autenticação e sem banco.

## Dados

- Cria tabelas de dados e insere linhas; escreve `_column_aliases` (nome
  original longo → coluna física). O api lê os aliases ao montar o schema e é
  quem renomeia/apaga tabelas.
- **Não cria tabelas de sistema:** o schema vem das migrations do api. Faça o
  deploy do api antes de uma versão do ingestion que dependa de schema novo.

## Auditoria

Eventos (`UPLOAD`, `INSERT`, `ANALYZE`) vão para o api por
`POST /internal/v1/events` com `X-Internal-Token`, em segundo plano
(`kit/audit_client.py`): o upload não espera a auditoria. Com o api fora por mais
de 3 tentativas, o evento sai inteiro no stderr com o prefixo `AUDIT_UNDELIVERED`.

## Configuração

- `DATABASE_URL`, `LOCAL_SCHEMA`
- `JWT_SECRET` — o mesmo do api (o token é verificado aqui, sem chamar o api)
- `INTERNAL_API_TOKEN` — envio de eventos ao api
- `AUDIT_SERVICE_URL` (opcional, default `http://api:5000`)

## Desenvolvimento

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
flake8 .
python -m pytest -q          # sem Postgres e sem api: tudo mockado
```

`kit/`, `db.py` e `tests/test_kit.py` são **cópia** do kit do api: não edite
aqui; altere em `api/kit`.

