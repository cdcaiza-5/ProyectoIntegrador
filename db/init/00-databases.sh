#!/bin/bash
# Contrato 7 §1 — dos bases con dueños distintos y sin conexión cruzada.
# Corre una sola vez, sobre un volumen de datos vacío.
#
# Durante la inicialización el socket local confía en el sistema, así que la
# migración se aplica con el usuario de la aplicación y los objetos le
# pertenecen; si se aplicara como superusuario, el servicio no podría escribir.

set -euo pipefail

provision() {
    local db="$1" role="$2" password="$3" schema="$4"

    psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
         -v db="$db" -v role="$role" -v pass="$password" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'role', :'pass')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role')\gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'db', :'role')
 WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db')\gexec
SELECT format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', :'db')\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'db', :'role')\gexec
SQL

    psql -v ON_ERROR_STOP=1 -U "$role" -d "$db" -f "$schema"
    echo "[init] base '$db' creada y migrada; dueño '$role'"
}

provision "$AUTH_DB_NAME"  "$AUTH_DB_USER"  "$AUTH_DB_PASSWORD"  /docker-entrypoint-initdb.d/10-auth-schema.sql
provision "$STEGO_DB_NAME" "$STEGO_DB_USER" "$STEGO_DB_PASSWORD" /docker-entrypoint-initdb.d/20-stego-schema.sql
