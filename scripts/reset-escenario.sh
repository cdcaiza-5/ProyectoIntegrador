#!/usr/bin/env bash
# Borra de verdad los usuarios de demostración y sus asignaciones.
# La API no expone DELETE /users a propósito, así que esto va por SQL.
#
# Uso:
#   ./scripts/reset-escenario.sh            # todos los usuarios menos el ADMIN
#   ./scripts/reset-escenario.sh --todo     # todos los usuarios: hay que repetir el bootstrap
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

COMPOSE="${COMPOSE:-docker compose}"
TODO=0
[ "${1:-}" = "--todo" ] && TODO=1

contar() {
    $COMPOSE exec -T db psql -U auth_app -d auth -tAc \
      "select count(*) || ' usuarios, ' || (select count(*) from auth.user_roles) || ' asignaciones' from auth.users;"
}

echo "antes: $(contar)"

if [ "$TODO" = "1" ]; then
    $COMPOSE exec -T db psql -U auth_app -d auth -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
DELETE FROM auth.revoked_tokens;
DELETE FROM auth.user_roles;
DELETE FROM auth.users;
COMMIT;
SQL
    echo "después: $(contar)"
    echo
    echo "no queda ningún usuario. Créalo otra vez:"
    echo "  docker compose exec auth python -m app.cli bootstrap-admin --username admin --email admin@espe.edu.ec"
else
    $COMPOSE exec -T db psql -U auth_app -d auth -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
-- se conserva la cuenta de administración: borrarla deja el sistema sin acceso
DELETE FROM auth.revoked_tokens
 WHERE subject_id IN (SELECT id FROM auth.users WHERE username <> 'admin');
DELETE FROM auth.user_roles
 WHERE user_id IN (SELECT id FROM auth.users WHERE username <> 'admin');
DELETE FROM auth.users WHERE username <> 'admin';
COMMIT;
SQL
    echo "después: $(contar)"
fi
