#!/usr/bin/env bash
# Levanta el stack, aprovisiona el administrador si falta y ejecuta la suite
# contra los servicios reales. Deja la salida en evidence/.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

ADMIN_PASSWORD="${TEST_ADMIN_PASSWORD:-AdminSegura2026!}"
ADMIN_EMAIL="${TEST_ADMIN_EMAIL:-admin@espe.edu.ec}"
COMPOSE="${COMPOSE:-docker compose}"
AUTH_PUBLIC_URL="${AUTH_PUBLIC_URL:-http://localhost:8080}"
STEGO_PUBLIC_URL="${STEGO_PUBLIC_URL:-http://localhost:8081}"

echo "== 1/5 · levantando la base"
$COMPOSE up -d db
for _ in $(seq 1 60); do
    $COMPOSE ps --format '{{.Service}} {{.Health}}' | grep -q 'db healthy' && break
    sleep 2
done

echo "== 2/5 · levantando AUTH y STEGO"
$COMPOSE up -d auth stego
for _ in $(seq 1 60); do
    ready=$($COMPOSE ps --format '{{.Health}}' | grep -c healthy || true)
    [ "$ready" -ge 3 ] && break
    sleep 2
done
$COMPOSE ps

echo "== 3/5 · aprovisionando el primer administrador (idempotente)"
printf '%s\n' "$ADMIN_PASSWORD" |
    $COMPOSE exec -T auth python -m app.cli bootstrap-admin \
        --username admin --email "$ADMIN_EMAIL" --password-stdin

mkdir -p evidence

echo "== 4/5 · suite funcional, de seguridad e integración"
$COMPOSE run --rm \
    -v "$PWD/tests:/tests:ro" \
    -v "$PWD/samples:/samples:ro" \
    -e AUTH_BASE_URL=http://auth:8080 \
    -e STEGO_BASE_URL=http://stego:8081 \
    -e TEST_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
    auth python -m pytest /tests -q -p no:cacheprovider 2>&1 | tee evidence/pytest.txt

echo "== 5/5 · T08 · AUTH inaccesible → 503 sin persistir"
TOKEN=$(curl -s -X POST "$AUTH_PUBLIC_URL/api/v1/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"identifier\":\"admin\",\"password\":\"$ADMIN_PASSWORD\"}" |
    python3 -c 'import json,sys;print(json.load(sys.stdin).get("access_token",""))')

{
    echo "# T08 — AUTH detenido antes del análisis"
    echo "antes: filas en stego.analyses = $($COMPOSE exec -T db psql -U stego_app -d stego -tAc 'select count(*) from stego.analyses')"
    $COMPOSE stop auth >/dev/null
    echo "petición con AUTH caído:"
    curl -s -o /dev/stdout -w '\nHTTP %{http_code}\n' -X POST "$STEGO_PUBLIC_URL/api/v1/steganography/analyze" \
        -H "Authorization: Bearer $TOKEN" -F "file=@samples/sample-clean.png" | head -20
    echo "después: filas en stego.analyses = $($COMPOSE exec -T db psql -U stego_app -d stego -tAc 'select count(*) from stego.analyses')"
    $COMPOSE start auth >/dev/null
} | tee evidence/T08-auth-caido.txt

echo
echo "Evidencias en evidence/. Suite en evidence/pytest.txt."
