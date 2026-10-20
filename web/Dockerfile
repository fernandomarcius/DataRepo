# Build stage
FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Serve stage — imagem unprivileged do nginx: roda como uid 101 e escuta em 8080,
# porque porta < 1024 exige root. Tag fixa, nunca `latest` (Handbook §10).
FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
# O entrypoint renderiza /etc/nginx/templates/*.template em /etc/nginx/conf.d/
# com envsubst (so as variaveis DATAREPO_*), substituindo o default.conf da imagem.
COPY templates/ /etc/nginx/templates/

# Nomes de servico da rede do compose. Em outro runtime basta sobrescrever.
ENV NGINX_ENVSUBST_FILTER=DATAREPO_ \
    DATAREPO_RESOLVER=127.0.0.11 \
    DATAREPO_API_UPSTREAM=api:5000 \
    DATAREPO_QUERY_UPSTREAM=api-query:5000 \
    DATAREPO_INGESTION_UPSTREAM=ingestion:5000

EXPOSE 8080

# wget vem no busybox da imagem alpine; nao ha curl.
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 \
  CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/healthz"]

CMD ["nginx", "-g", "daemon off;"]
