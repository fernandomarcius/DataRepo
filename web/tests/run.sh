#!/usr/bin/env bash
# Teste de roteamento do nginx do web contra o nginx de verdade.
#
#   tests/run.sh          sobe web + stubs, confere tests/routes.tsv, derruba
#
# Confere, para cada linha do contrato: o servico que recebeu, o caminho
# intacto (com query string) e que o X-Forwarded-For forjado pelo cliente foi
# descartado; que as rotas do SPA devolvem o index.html; e que /internal nao
# passa pela borda.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1

COMPOSE=(docker compose -f docker-compose.test.yml)
BASE="http://127.0.0.1:18080"

limpar() { "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true; }
trap limpar EXIT

"${COMPOSE[@]}" up -d --build --wait --wait-timeout 120 >/dev/null || {
  "${COMPOSE[@]}" logs
  echo "::error::web nao subiu"
  exit 1
}

for _ in $(seq 1 30); do
  curl -fsS "$BASE/healthz" >/dev/null 2>&1 && break
  sleep 1
done

falhas=0
total=0

conferir_rota() {
  local caminho="$1" esperado="$2"
  total=$((total + 1))
  local corpo
  corpo=$(curl -sS -H "X-Forwarded-For: 6.6.6.6" "$BASE$caminho") || corpo=""
  python3 - "$caminho" "$esperado" "$corpo" <<'PY' || falhas=$((falhas + 1))
import json, sys
caminho, esperado, corpo = sys.argv[1:4]
try:
    r = json.loads(corpo)
except ValueError:
    print(f"  ✗ {caminho}: resposta nao e do stub: {corpo[:120]!r}")
    sys.exit(1)
problemas = []
if r.get("service") != esperado:
    problemas.append(f"foi para {r.get('service')!r}, esperado {esperado!r}")
if r.get("path") != caminho:
    problemas.append(f"caminho chegou como {r.get('path')!r}")
if "6.6.6.6" in (r.get("xff") or ""):
    problemas.append("X-Forwarded-For forjado pelo cliente chegou ao servico")
if problemas:
    print(f"  ✗ {caminho}: " + "; ".join(problemas))
    sys.exit(1)
print(f"  ✓ {caminho} -> {esperado}")
PY
}

conferir_spa() {
  local caminho="$1"
  total=$((total + 1))
  if curl -fsS "$BASE$caminho" | grep -qi '<div id="root"'; then
    echo "  ✓ $caminho -> index.html do SPA"
  else
    echo "  ✗ $caminho nao devolveu o index.html do SPA"
    falhas=$((falhas + 1))
  fi
}

conferir_status() {
  local caminho="$1" esperado="$2"
  total=$((total + 1))
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE$caminho")
  if [ "$status" = "$esperado" ]; then
    echo "  ✓ $caminho -> HTTP $status"
  else
    echo "  ✗ $caminho -> HTTP $status, esperado $esperado"
    falhas=$((falhas + 1))
  fi
}

echo "== contrato de roteamento (routes.tsv) =="
while IFS=$'\t' read -r _regra caminho servico; do
  case "$_regra" in ''|\#*) continue ;; esac
  if [ "$servico" = spa ]; then
    conferir_spa "$caminho"
  else
    conferir_rota "$caminho" "$servico"
  fi
done < routes.tsv

echo "== o que nao pode passar pela borda =="
conferir_status /internal/v1/events 404
conferir_status /api/v1/internal/v1/events 404
conferir_status /healthz 200

echo
if [ "$falhas" -gt 0 ]; then
  "${COMPOSE[@]}" logs web | tail -30
  echo "::error::$falhas de $total verificacoes de roteamento falharam"
  exit 1
fi
echo "roteamento ok: $total verificacoes"
