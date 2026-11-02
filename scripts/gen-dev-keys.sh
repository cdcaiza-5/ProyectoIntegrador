#!/usr/bin/env bash
# Genera el par RSA de desarrollo. La actividad 04 define `kid` y rotación reales.
set -euo pipefail

dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.secrets"
mkdir -p "$dir"

if [ -s "$dir/jwt_private.pem" ]; then
    echo "ya existe $dir/jwt_private.pem; no se sobrescribe"
    exit 0
fi

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$dir/jwt_private.pem" 2>/dev/null
openssl rsa -in "$dir/jwt_private.pem" -pubout -out "$dir/jwt_public.pem" 2>/dev/null
# `secrets:` de Compose conserva dueño y modo del host, y el contenedor corre
# sin privilegios (uid 10001): con 600 la clave sería ilegible dentro de AUTH.
# Es una clave de desarrollo, vive en .secrets/ (ignorado por git) y nunca se
# versiona; la de producción la entrega un gestor de secretos.
chmod 644 "$dir/jwt_private.pem"
chmod 644 "$dir/jwt_public.pem"

echo "claves de desarrollo generadas en $dir"
