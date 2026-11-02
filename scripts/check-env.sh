#!/usr/bin/env bash
# Comprueba que la contraseña con la que se provisionó cada base es la misma
# que lee el servicio. Desajustada, el servicio arranca y falla al conectar.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
status=0

read_var() { sed -n "s/^$2=//p" "$1" 2>/dev/null | head -1; }

compare() {
    local label="$1" expected="$2" file="$3"
    if [ "$(read_var "$file" DB_PASSWORD)" != "$expected" ]; then
        echo "ERROR  $label: DB_PASSWORD de ${file#"$root"/} no coincide con el .env raíz" >&2
        status=1
    fi
}

compare AUTH  "$(read_var "$root/.env" AUTH_DB_PASSWORD)"  "$root/auth/.env"
compare STEGO "$(read_var "$root/.env" STEGO_DB_PASSWORD)" "$root/stego/.env"

if [ "$status" -eq 0 ]; then
    echo "contraseñas de base consistentes"
fi

exit "$status"
