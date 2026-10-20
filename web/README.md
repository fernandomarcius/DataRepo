# datarepo-web

Frontend do DataRepo (React + Vite) e o **nginx de borda** do sistema: um
único container, o único com porta publicada (5173 e 5000, as portas do antigo
monólito). Parte do DataRepo: ver o repositório do api (DataRepo), ADR 0004.

## O que o nginx faz

| Caminho | Destino |
|---|---|
| `/`, rotas do SPA | `index.html` e assets do build |
| `/api/v1/query` | `api-query` (mesma imagem do api; consultas longas isoladas) |
| `/api/v1/upload`, `/map-file`, `/inspect-headers`, `POST /api/v1/tables/<t>/data` | `ingestion` |
| todo o resto de `/api/` | `api` |
| `/internal/*` | 404 — rotas servico-a-servico nunca saem pela borda |
| `/healthz` | 200, do próprio nginx |

- Sobrescreve `X-Forwarded-For` com o IP de quem conectou (a borda descarta o
  valor enviado pelo cliente); api e ingestion confiam em exatamente um salto.
- Uploads de até 100 MB e timeouts de 300 s.
- Upstreams configuráveis por ambiente (`DATAREPO_API_UPSTREAM`, `DATAREPO_QUERY_UPSTREAM`,
  `DATAREPO_INGESTION_UPSTREAM`, `DATAREPO_RESOLVER`); defaults da rede do compose no
  `Dockerfile`. Resolução por requisição: o nginx sobe mesmo com um serviço fora.

Configuração: `templates/default.conf.template`.

## Contrato de roteamento

`tests/routes.tsv` lista cada rota da API, um caminho de exemplo e o destino.
`tests/run.sh` sobe **este** nginx contra serviços-stub e confere cada linha
(destino, caminho intacto, `X-Forwarded-For` forjado descartado), o SPA e o
bloqueio de `/internal`. No repositório do api, `tools/check-route-contract.py`
confere que toda rota declarada no api e no ingestion aparece aqui.

Rota nova no api ou no ingestion → linha nova aqui (e `location`, se o prefixo
não cair no destino certo).

## Desenvolvimento

```bash
npm ci
npm run dev        # Vite em :5173, /api via proxy para :5000 (API_PROXY_TARGET)
npm run build
npm run lint
bash tests/run.sh  # roteamento do nginx (Docker)
```

A API local vem da stack de dev do repositório do api (`deploy/docker-compose.dev.yml`).

## Sob um prefixo (plataforma, example.com/dataapp)

O mesmo código roda na raiz de um host (este nginx), sob
`/workloads/{tenant}/{serviço}/` numa plataforma e sob qualquer caminho de um
proxy na frente dele (ex.: `example.com/dataapp`, por um Worker
do Cloudflare). Cada salto tira o seu pedaço do caminho antes de repassar; só o
navegador conhece o prefixo, então nenhuma URL absoluta do app é literal:

- `src/prefixo.js` tira o prefixo da URL de onde o próprio bundle foi carregado
  (`import.meta.url`, `<prefixo>/assets/…`); na raiz ele é `''`;
- a API usa `${prefixo()}/api/v1`, o Router usa `basename={prefixo()}` e
  arquivos de `public/` usam `rota('/logo.svg')`;
- os assets do Vite seguem `VITE_BASE` (padrão `/`). Um empacotamento sob prefixo compila com `VITE_BASE=./` e o nginx de lá
  reescreve os caminhos relativos do `index.html` pela profundidade da URL.

Na raiz nada muda: sem `VITE_BASE`, o build é idêntico ao anterior.

