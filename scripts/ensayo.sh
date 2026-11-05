#!/usr/bin/env bash
# Ensayo de la sustentación, en el orden exacto que exige el enunciado (§3).
# Uso: ./ensayo.sh   (con el stack levantado y las muestras generadas)
set -uo pipefail

AUTH=http://localhost:8080
STEGO=http://localhost:8081
ADMIN_PASS=AdminSegura2026!

b() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }
body() { python3 -c 'import sys,json;print(json.dumps(json.load(sys.stdin),ensure_ascii=False)[:200])'; }
st() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
tok() { curl -s -X POST "$AUTH/api/v1/auth/login" -H 'Content-Type: application/json' \
        -d "{\"identifier\":\"$1\",\"password\":\"$2\"}" \
        | python3 -c 'import sys,json;print(json.load(sys.stdin).get("access_token",""))'; }
idof() { python3 -c 'import sys,json;print(json.load(sys.stdin).get("id",""))'; }
roleid() { curl -s "$AUTH/api/v1/roles?limit=100" -H "Authorization: Bearer $1" \
           | python3 -c "import sys,json;print([r['id'] for r in json.load(sys.stdin)['items'] if r['name']=='$2'][0])"; }

ADMIN=$(tok admin "$ADMIN_PASS")
[ -z "$ADMIN" ] && { echo "no se pudo entrar como admin; ¿corriste el bootstrap-admin?"; exit 1; }
ANALYST=$(roleid "$ADMIN" ANALYST)
USERROLE=$(roleid "$ADMIN" USER)

b "1 · Cada servicio responde desde su propia API"
printf 'AUTH  /health → '; curl -s $AUTH/health; echo
printf 'STEGO /health → '; curl -s $STEGO/health; echo

b "2 · Un usuario con dos roles"
ANA=$(curl -s -X POST $AUTH/api/v1/users -H "Authorization: Bearer $ADMIN" -H 'Content-Type: application/json' \
      -d '{"username":"ana","email":"ana@espe.edu.ec","password":"AnaSegura2026!"}' | idof)
curl -s -o /dev/null -X POST $AUTH/api/v1/user-roles -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' -d "{\"user_id\":\"$ANA\",\"role_id\":\"$ANALYST\"}"
curl -s -o /dev/null -X POST $AUTH/api/v1/user-roles -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' -d "{\"user_id\":\"$ANA\",\"role_id\":\"$USERROLE\"}"
A_ANA=$(tok ana AnaSegura2026!)
printf 'perfil de ana → '; curl -s $AUTH/api/v1/auth/profile -H "Authorization: Bearer $A_ANA" | body

b "3 · Un rol asignado a dos usuarios"
BETO=$(curl -s -X POST $AUTH/api/v1/users -H "Authorization: Bearer $ADMIN" -H 'Content-Type: application/json' \
       -d '{"username":"beto","email":"beto@espe.edu.ec","password":"BetoSegura2026!"}' | idof)
ASG_BETO=$(curl -s -X POST $AUTH/api/v1/user-roles -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' -d "{\"user_id\":\"$BETO\",\"role_id\":\"$ANALYST\"}" | idof)
A_BETO=$(tok beto BetoSegura2026!)
printf 'perfil de beto → '; curl -s $AUTH/api/v1/auth/profile -H "Authorization: Bearer $A_BETO" | body
echo "asignación de beto: $ASG_BETO   (se usa en el paso 6)"

b "4 · El JWT de AUTH sirve contra STEGO"
printf 'analyze con el token de ana → HTTP '; st -X POST $STEGO/api/v1/steganography/analyze \
  -H "Authorization: Bearer $A_ANA" -F "file=@samples/sample-clean.png"; echo

b "5 · Denegaciones"
printf 'sin token               → HTTP '; st -X POST $STEGO/api/v1/steganography/analyze -F "file=@samples/sample-clean.png"; echo
printf 'token manipulado        → HTTP '; st -X POST $STEGO/api/v1/steganography/analyze \
  -H "Authorization: Bearer no.es.un.jwt" -F "file=@samples/sample-clean.png"; echo
CARLA=$(curl -s -X POST $AUTH/api/v1/users -H "Authorization: Bearer $ADMIN" -H 'Content-Type: application/json' \
        -d '{"username":"carla","email":"carla@espe.edu.ec","password":"CarlaSegura2026!"}' | idof)
A_CARLA=$(tok carla CarlaSegura2026!)
printf 'autenticada y sin rol   → HTTP '; st -X POST $STEGO/api/v1/steganography/analyze \
  -H "Authorization: Bearer $A_CARLA" -F "file=@samples/sample-clean.png"; echo
printf '   cuerpo → '; curl -s -X POST $STEGO/api/v1/steganography/analyze \
  -H "Authorization: Bearer $A_CARLA" -F "file=@samples/sample-clean.png" | body

b "6 · Retirar el rol con el mismo JWT todavía vigente"
printf 'beto antes de retirar   → HTTP '; st -X POST $STEGO/api/v1/steganography/analyze \
  -H "Authorization: Bearer $A_BETO" -F "file=@samples/sample-clean.png"; echo
curl -s -o /dev/null -X DELETE "$AUTH/api/v1/user-roles/$ASG_BETO" -H "Authorization: Bearer $ADMIN"
printf 'tras DELETE, mismo JWT  → HTTP '; st -X POST $STEGO/api/v1/steganography/analyze \
  -H "Authorization: Bearer $A_BETO" -F "file=@samples/sample-clean.png"; echo

b "7 · STEGO falla seguro con AUTH caído"
docker compose stop auth >/dev/null 2>&1
printf 'analyze con AUTH apagado → HTTP '; st -X POST $STEGO/api/v1/steganography/analyze \
  -H "Authorization: Bearer $A_ANA" -F "file=@samples/sample-clean.png"; echo
printf '   cuerpo → '; curl -s -X POST $STEGO/api/v1/steganography/analyze \
  -H "Authorization: Bearer $A_ANA" -F "file=@samples/sample-clean.png" | body
docker compose start auth >/dev/null 2>&1
sleep 6

b "8 · Imagen de referencia vs. imagen con carga LSB"
for f in sample-clean.png sample-lsb.png; do
  printf '%-18s → ' "$f"
  curl -s -X POST $STEGO/api/v1/steganography/analyze -H "Authorization: Bearer $A_ANA" \
    -F "file=@samples/$f" \
    | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("status"),"·",d.get("action"),"· score",d.get("indicators",{}).get("anomaly_score"))'
done
