# Guion de sustentación — Backend V1 (AUTH + STEGO)

**Asignatura:** Desarrollo Software Seguro · ESPE · DCCO
**Entrega y defensa:** miércoles 4 de noviembre de 2026
**Duración objetivo:** 13 minutos de demostración + preguntas
**Documento de referencia:** `entrega/DOCUMENTO-TECNICO.md` (cifras, rutas y códigos citados aquí salen de ahí)

> **Estado de este guion.** Los comandos corresponden a los contratos congelados y a las rutas de
> `docker-compose.yml`. Varios dependen de actividades que aún no están cerradas (A02, A04, A06, A07, A08).
> El ensayo completo —y por tanto la evidencia de que el guion corre de punta a punta— es
> `⟨PENDIENTE · A13⟩`. Este archivo se lee antes de cada ensayo, no la noche anterior.

---

## 0. Montaje de la demostración

### 0.1 Terminales

| Terminal | Para qué | Directorio |
|---|---|---|
| **T1** | `docker compose` y `psql`: estado, arranque, parada, evidencias de base | raíz del repositorio |
| **T2** | `curl` contra AUTH y STEGO: todo el flujo REST | raíz del repositorio |

Dos terminales, no tres: cada cambio de ventana cuesta segundos y desconcentra. La fuente del terminal en
18–20 pt; el proyector degrada el contraste y el evaluador tiene que leer los códigos HTTP.

### 0.2 Variables de la sesión

Se definen una vez al inicio de T2 y no se vuelven a escribir:

```bash
export AUTH=http://localhost:8080/api/v1
export STEGO=http://localhost:8081/api/v1

# Muestra el código HTTP y el cuerpo. El código es lo que se evalúa.
call() {
  local out code
  out=$(mktemp)
  code=$(curl -sS -o "$out" -w '%{http_code}' "$@")
  printf '\nHTTP %s\n' "$code"
  jq . "$out" 2>/dev/null || cat "$out"
  printf '\n'
}
```

`call` sirve para todo el guion: evita repetir `-w '%{http_code}'` y evita que un `200` se confunda con un
`403` porque el cuerpo es parecido. Cuando además hace falta el `id` de la respuesta (asignaciones), se usa
su variante `save`, que guarda el cuerpo en un archivo:

```bash
save() {   # save <archivo> <argumentos de curl...>
  CODE=$(curl -sS -o "$1" -w '%{http_code}' "${@:2}")
  printf '\nHTTP %s\n' "$CODE"
  jq . "$1" 2>/dev/null || cat "$1"
  printf '\n'
}
```

### 0.3 Credenciales de la demostración

Todo lo de esta sección se ejecuta **en T2**, y todas las variables (`ANA_PASS`, `ADMIN_TOKEN`, `ANA_TOKEN`,
`ANA_ID`…) viven en esa misma shell: una variable creada en T1 no existe en T2.

Son **desechables** y el entorno se destruye al terminar (contrato 5 §5). Se escriben con entrada oculta
para que no queden en el historial del shell ni en `ps`:

```bash
read -rsp 'contraseña de ana: ' ANA_PASS; echo
read -rsp 'contraseña de luis: ' LUIS_PASS; echo
```

> Las contraseñas de demostración se eligen sin comillas dobles, sin barras invertidas, sin `!` y sin
> acentos: los cuerpos JSON de `curl` se escriben en la línea de comandos y esos caracteres obligan a
> escapar y hacen fallar la petición en plena defensa. Mínimo 12 caracteres, como exige el bootstrap.

| Sujeto | Rol(es) | Para qué |
|---|---|---|
| `admin.demo` | ADMIN | Creado por bootstrap; administra el resto |
| `ana.perez` | ANALYST + USER | **Dos roles**. Es quien analiza y luego pierde el permiso |
| `luis.vega` | USER | **Segundo usuario del rol USER**. Es el `403` del paso 5 |

### 0.4 Qué NO se prepara de antemano

El enunciado exige crear el usuario, asignar roles y hacer login **durante la sustentación**. Se prepara
solo lo que no demuestra nada: los contenedores arriba, el ADMIN por bootstrap y las muestras generadas.
Los usuarios y las asignaciones se crean en vivo.

---

## 1. Preparación previa (fuera del tiempo de exposición)

Ejecutar 10 minutos antes, con la sala aún vacía:

```bash
# 1. Entorno y claves
cp -n .env.example .env; cp -n auth/.env.example auth/.env; cp -n stego/.env.example stego/.env
./scripts/gen-dev-keys.sh
./scripts/check-env.sh

# 2. Arranque limpio (borra datos de ensayos anteriores)
docker compose down -v
docker compose up -d --build
docker compose ps

# 3. Salud de los dos servicios
curl -s http://localhost:8080/health; echo
curl -s http://localhost:8081/health; echo

# 4. JWKS responde y publica un kid
curl -s http://localhost:8080/.well-known/jwks.json | jq -r '.keys[].kid'

# 5. Primer administrador (no hay usuarios sembrados a propósito)
#    La contraseña se pide por terminal; --username y --email no son secretos.
docker compose exec auth python -m app.cli bootstrap-admin \
    --username admin.demo --email admin.demo@espe.edu.ec

# 6. Muestras
sha256sum samples/sample-clean.png samples/sample-lsb.png samples/sample-clean.bmp \
          samples/sample-corrupt.png samples/sample-fake.png samples/sample-huge.png
```

> Si los `.env` ya existían de un ensayo anterior, `cp -n` no los sobrescribe y `check-env.sh` puede fallar
> por contraseñas distintas. Igualar `AUTH_DB_PASSWORD` y `STEGO_DB_PASSWORD` del `.env` raíz con los
> `DB_PASSWORD` de cada servicio **antes** del `down -v`: el volumen nuevo se crea con las del `.env` raíz,
> y si divergen el servicio arranca y muere al conectar.

**Checklist de "listo para empezar":**

- [ ] `docker compose ps` muestra `auth`, `stego` y `db` en `running (healthy)`.
- [ ] Los dos `/health` responden `200`.
- [ ] `jwks.json` devuelve al menos un `kid` y ningún campo privado (`d`, `p`, `q`).
- [ ] El bootstrap terminó y dejó `admin.demo` con rol ADMIN.
- [ ] Las seis muestras existen y su `sha256` está anotado.
- [ ] `evidence/` está vacío o con las capturas de ensayo, nunca con resultados que no se vayan a mostrar.
- [ ] El navegador está cerrado; notificaciones silenciadas.
- [ ] `⟨PENDIENTE · A13⟩` Ensayo completo ejecutado al menos una vez sin errores.

---

## 2. Resumen cronometrado

| Paso | Inicio | Fin | Qué se demuestra | Escenario |
|---|---|---|---|---|
| 0 | 0:00 | 0:45 | Los dos servicios están arriba y son autónomos | T01 |
| 1 | 0:45 | 2:15 | Usuario con **dos roles** persistidos en N:M | T05 |
| 2 | 2:15 | 3:15 | Un rol asignado a **dos usuarios** | T05 |
| 3 | 3:15 | 4:15 | Login y anatomía del JWT: **no lleva roles** | T02 |
| 4 | 4:15 | 5:45 | Análisis con el JWT del usuario | T09 (parcial) |
| 5 | 5:45 | 8:15 | Denegaciones `401` y `403` | T02, T03, T04 |
| 6 | 8:15 | 9:45 | Retirar el rol y **reutilizar el JWT vivo** | T07 |
| 7 | 9:45 | 10:45 | AUTH caído: `503` y **fallo cerrado** | T08 |
| 8 | 10:45 | 12:45 | Imagen limpia vs. imagen con carga LSB | T09, T10 |
| 9 | 12:45 | 13:15 | Cierre: qué se demostró y qué no | — |

El orden es el del enunciado (§3) y no se altera: cada paso depende del anterior. El `503` se demuestra en
el paso 7 y no en el 5 porque exige parar AUTH, y pararlo dos veces cuesta 40 segundos sin añadir evidencia.

**El reloj corre en contra.** El access token dura 900 s: si la demostración se pasa de 15 minutos desde el
login del paso 3, el token de ana vence y hay que renovarlo. Eso no es un fallo, es el diseño funcionando;
se dice en voz alta («el token venció, 900 s, renuevo y sigo») y se continúa. Por eso el administrador se
autentica al principio y se reutiliza: su token cubre los 13 minutos con margen.

---

## 3. Paso 0 — Preflight y arranque autónomo (0:45)

**Ejecutar (T1):**

```bash
docker compose ps
docker compose stop stego && sleep 1 && curl -s -o /dev/null -w 'AUTH con STEGO detenido: %{http_code}\n' http://localhost:8080/health
docker compose up -d stego
```

**Decir:**

> «Son dos microservicios, no dos carpetas de la misma aplicación. Cada uno tiene su contenedor, su
> configuración y su ciclo de vida: acabo de detener STEGO y AUTH siguió respondiendo su healthcheck. La
> base de datos es infraestructura: una instancia, dos bases con usuarios distintos y sin acceso cruzado, y
> el puerto 5432 no está publicado.»

**Mostrar:** la tabla de `docker compose ps` con tres servicios y los dos `200` de `/health`.

**Plan B:**
- Si algún servicio no está `healthy`: `docker compose logs --tail=50 auth` (o `stego`) y `docker compose up -d --build`.
- Si el `db` no está sano, el resto no arranca: `docker compose restart db` y esperar el `healthcheck` (10 s de `start_period`).
- Si el arranque falla por interpolación de Compose, falta `POSTGRES_SUPERUSER_PASSWORD` en `.env`: completarlo y repetir.
- Si no hay tiempo: saltar el `stop stego` y decir el argumento con el `docker-compose.yml` abierto en T1, señalando los tres servicios y las dos redes. La evidencia de T01 está en `evidence/T01/` `⟨PENDIENTE · A12⟩`.

---

## 4. Paso 1 — Crear un usuario con dos roles (1:30)

**Ejecutar (T2). Primero el token de administrador:**

```bash
read -rsp 'contraseña de admin.demo: ' ADMIN_PASS; echo
ADMIN_TOKEN=$(curl -s -X POST "$AUTH/auth/login" -H 'Content-Type: application/json' \
  -d "{\"identifier\":\"admin.demo\",\"password\":\"$ADMIN_PASS\"}" | jq -r .access_token)
echo "${ADMIN_TOKEN:0:24}… (longitud ${#ADMIN_TOKEN})"

# Ids de los roles sembrados
ANALYST_ID=$(curl -s "$AUTH/roles" -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.items[] | select(.name=="ANALYST") | .id')
USER_ID=$(curl -s "$AUTH/roles" -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.items[] | select(.name=="USER") | .id')
echo "ANALYST=$ANALYST_ID"; echo "USER=$USER_ID"
```

**Crear a ana y asignarle los dos roles:**

```bash
ANA_ID=$(curl -s -X POST "$AUTH/users" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"ana.perez\",\"email\":\"ana.perez@espe.edu.ec\",\"password\":\"$ANA_PASS\"}" | jq -r .id)
echo "ana.perez = $ANA_ID"

save /tmp/ur-analyst.json -X POST "$AUTH/user-roles" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' -d "{\"user_id\":\"$ANA_ID\",\"role_id\":\"$ANALYST_ID\"}"
UR_ANALYST=$(jq -r .id /tmp/ur-analyst.json)

save /tmp/ur-user.json -X POST "$AUTH/user-roles" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' -d "{\"user_id\":\"$ANA_ID\",\"role_id\":\"$USER_ID\"}"
```

**Evidencia en base (T1):**

```bash
docker compose exec -T db psql -U auth_app -d auth -c "
SELECT u.username, r.name, ur.status, ur.assigned_at
FROM auth.user_roles ur
JOIN auth.users u ON u.id = ur.user_id
JOIN auth.roles r ON r.id = ur.role_id
WHERE u.username = 'ana.perez' ORDER BY r.name;"
```

**Decir:**

> «La relación muchos a muchos no está en una columna ni en un arreglo en memoria: está en la tabla
> `user_roles`, con clave foránea a `users` y a `roles` y una restricción `UNIQUE (user_id, role_id)` que
> impide duplicados. Ana acumula ANALYST y USER; la decisión de autorización será la unión de ambos roles.
> El `201` de cada asignación y las dos filas que aparecen en la base son la misma cosa vista desde la API y
> desde el modelo.»

**Mostrar:** los dos `201`, el `id` de ana y las dos filas de la consulta con `status = active`.

**Plan B:**
- `409 USER_EXISTS`: ana ya existe de un ensayo anterior. Recuperar su id con
  `curl -s "$AUTH/users?limit=100" -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.items[] | select(.username=="ana.perez") | .id'`
  y continuar. No hace falta reiniciar el entorno.
- `409 ASSIGNMENT_EXISTS`: la asignación ya existía. **Convertirlo en evidencia de T06**: repetir el mismo
  `POST`, mostrar el `409` y consultar que el `count` sigue siendo 1. Es un escenario de la rúbrica, no un error.
- `403` con el token del admin: el token no tiene rol ADMIN. Comprobar con
  `curl -s "$AUTH/auth/profile" -H "Authorization: Bearer $ADMIN_TOKEN" | jq`, y si el bootstrap no se
  ejecutó, ejecutarlo en T1.
- `422` al crear el usuario: el esquema exige contraseña de **12 caracteres o más** y un correo con formato
  válido (validado como `EmailStr`). Ajustar y repetir.

---

## 5. Paso 2 — Asignar un rol a dos usuarios (1:00)

**Ejecutar (T2):**

```bash
LUIS_ID=$(curl -s -X POST "$AUTH/users" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"luis.vega\",\"email\":\"luis.vega@espe.edu.ec\",\"password\":\"$LUIS_PASS\"}" | jq -r .id)
echo "luis.vega = $LUIS_ID"

call -X POST "$AUTH/user-roles" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' -d "{\"user_id\":\"$LUIS_ID\",\"role_id\":\"$USER_ID\"}"
```

**Evidencia (T1):**

```bash
docker compose exec -T db psql -U auth_app -d auth -c "
SELECT r.name AS rol, count(*) AS usuarios, string_agg(u.username, ', ' ORDER BY u.username) AS quienes
FROM auth.user_roles ur
JOIN auth.users u ON u.id = ur.user_id
JOIN auth.roles r ON r.id = ur.role_id
WHERE ur.status = 'active'
GROUP BY r.name ORDER BY r.name;"
```

**Decir:**

> «El rol USER queda asignado a dos usuarios distintos. La cardinalidad se ve en las dos direcciones: ana
> tiene dos roles y USER tiene dos usuarios. Ninguna de las dos asignaciones comparte fila; son dos filas de
> `user_roles` que apuntan al mismo `role_id` con `user_id` distinto, y la restricción única permite
> exactamente eso porque la unicidad es del par, no de cada columna por separado.»

**Mostrar:** el `201` de luis y la consulta agregada con `USER | 2 | ana.perez, luis.vega`.

**Plan B:**
- Si el agregado muestra `USER | 1`, la asignación de ana en el paso 1 falló: repetirla y volver.
- Si luis ya existía del ensayo: recuperar su id como en el paso 1.
- Si el `PATCH`/`POST` devuelve `404 ROLE_NOT_FOUND`, el `USER_ID` quedó vacío porque el `jq` no encontró el
  nombre: verificar con `curl -s "$AUTH/roles" -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.items[].name'`.

---

## 6. Paso 3 — Login y anatomía del token (1:00)

**Ejecutar (T2):**

```bash
ANA_LOGIN=$(curl -s -X POST "$AUTH/auth/login" -H 'Content-Type: application/json' \
  -d "{\"identifier\":\"ana.perez\",\"password\":\"$ANA_PASS\"}")
ANA_TOKEN=$(printf '%s' "$ANA_LOGIN" | jq -r .access_token); export ANA_TOKEN
echo "token de ana: ${#ANA_TOKEN} caracteres"

# Qué hay dentro del token: se decodifica el payload, no se verifica
python3 - <<'PY'
import base64, json, os
p = os.environ["ANA_TOKEN"].split(".")[1]
p += "=" * (-len(p) % 4)
claims = json.loads(base64.urlsafe_b64decode(p))
print(json.dumps(claims, indent=2, ensure_ascii=False))
print("exp - iat =", claims["exp"] - claims["iat"], "segundos")
print("¿tiene roles?", "SÍ" if any(k.lower() in {"roles", "role", "permissions", "scope"}
                                   for k in claims) else "NO")
PY

# El perfil, con roles leídos de la base en esta petición
call "$AUTH/auth/profile" -H "Authorization: Bearer $ANA_TOKEN"
```

**Decir:**

> «El login devuelve un JWT firmado con RS256 y 900 segundos de vigencia. Si decodifico el payload veo
> `iss`, `sub`, `aud`, `iat`, `exp`, `jti`, `token_use` y `username`; **no hay roles**. Es deliberado: el
> token identifica la sesión, no autoriza. Los roles que muestra el perfil los acaba de leer AUTH de la base
> en esta petición, no vienen del token. Por eso el mismo token puede dejar de servir sin haber expirado: lo
> veremos en el paso 6.»

**Mostrar:** el payload sin roles, `exp - iat = 900`, `iss = auth-service`, `aud` con `auth-api` y
`stego-api`, y el `200` del perfil con los roles.

**Plan B:**
- `401 AUTH_INVALID_CREDENTIALS`: identificador o contraseña mal escritos. Probar con
  `{"identifier":"ana.perez@espe.edu.ec", ...}`: el campo acepta correo o usuario.
- `429 RATE_LIMITED`: se agotaron los 5 intentos por minuto. **Decirlo en voz alta** —es el rate limit
  funcionando— y esperar 60 s o continuar con un reintento limpio. Si el docente pregunta, ese `429` es
  evidencia de C-05.
- Si el campo del token no se llama `access_token`, ver el cuerpo completo con `call` y ajustar el `jq`.
  El nombre exacto de los campos de la respuesta de login no está congelado en el contrato 1; el de
  `/internal/service-token` sí (`access_token`), y es la convención que se sigue.
- Si `python3` no está en el host, el bloque de decodificación se ejecuta dentro de AUTH:
  `docker compose exec -T auth python -c "import base64,json,os,sys; p=sys.argv[1].split('.')[1]; p+='='*(-len(p)%4); print(json.loads(base64.urlsafe_b64decode(p)))" "$ANA_TOKEN"`.

---

## 7. Paso 4 — Analizar una imagen con el JWT (1:30)

**Ejecutar (T2). Una sola petición: guarda el cuerpo y muestra el código:**

```bash
OUT=$(mktemp)
CODE=$(curl -sS -o "$OUT" -w '%{http_code}' -X POST "$STEGO/steganography/analyze" \
  -H "Authorization: Bearer $ANA_TOKEN" \
  -F "file=@samples/sample-clean.png" \
  -F "note=demostracion T09 - imagen de referencia")
echo "HTTP $CODE"
jq . "$OUT"
AID=$(jq -r '.analysis_id // empty' "$OUT")
echo "analysis_id=$AID"
```

**Decir:**

> «STEGO recibe el archivo por multipart. Antes de abrir el archivo valida dos cosas: la firma y los claims
> del token, que hace localmente con la clave pública que obtiene por JWKS, y la decisión vigente, que pide a
> AUTH con un token de servicio propio. Solo si las dos pasan toca el archivo. La respuesta trae el
> `analysis_id`, el `sha256`, la técnica, los indicadores y la acción aplicada.»

**Mostrar:** el `201`, `technique: lsb_statistical_analysis`, `sha256`, `indicators.anomaly_score` y
`indicators.threshold`, y `action`.

**Plan B:**
- `401`: el token de ana venció (900 s). Volver a hacer login; **es el comportamiento diseñado**, decirlo.
- `403`: la asignación ANALYST no se creó. Comprobarlo con la consulta del paso 1.
- `503 AUTHORIZATION_UNAVAILABLE`: STEGO no alcanza AUTH. `docker compose logs --tail=30 stego` y verificar
  `STEGO_AUTH_BASE_URL=http://auth:8080`. Mientras se arregla, seguir con el paso 5: las denegaciones
  funcionan igual.
- `415`/`422`: ruta de la muestra equivocada. `ls -l samples/`.
- Si el análisis devuelve `no_concluyentes` sobre la muestra limpia, mostrarlo y explicar la guarda
  (imagen pequeña o pocas parejas) antes de seguir; el paso 8 necesita muestras analizables.

---

## 8. Paso 5 — Denegaciones `401` y `403` (2:30)

El `503` va en el paso 7, que es su escenario natural (AUTH caído).

### 5.a Sin token → `401 TOKEN_MISSING`

```bash
call -X POST "$STEGO/steganography/analyze" -F "file=@samples/sample-clean.png"
```

**Decir:** «Sin cabecera `Authorization` no hay sujeto. `401`: no sé quién eres. No se lee el archivo.»

### 5.b Token manipulado → `401 TOKEN_INVALID`

```bash
TAMPERED="${ANA_TOKEN}x"     # un carácter de más en la firma: cambia seguro y la invalida
call -X POST "$STEGO/steganography/analyze" -H "Authorization: Bearer $TAMPERED" \
  -F "file=@samples/sample-clean.png"
```

**Decir:** «Un solo carácter alterado invalida la firma RS256. No hay forma de cambiar el payload ni de
cambiar la firma sin la clave privada, que solo tiene AUTH.»

### 5.c `alg: none` → `401 TOKEN_INVALID` (20 s, si el tiempo lo permite)

```bash
NONE_TOKEN=$(python3 - <<'PY'
import base64, json
def b64(o):
    return base64.urlsafe_b64encode(json.dumps(o, separators=(",", ":")).encode()).rstrip(b"=").decode()
h = {"alg": "none", "typ": "JWT", "kid": "auth-2026-11"}
p = {"iss": "auth-service", "sub": "00000000-0000-4000-8000-000000000000",
     "aud": ["auth-api", "stego-api"], "token_use": "access"}
print(b64(h) + "." + b64(p) + ".")
PY
)
call -X POST "$STEGO/steganography/analyze" -H "Authorization: Bearer $NONE_TOKEN" \
  -F "file=@samples/sample-clean.png"
```

**Decir:** «El algoritmo está en una lista cerrada que solo admite RS256. Un token sin firma se rechaza por
el paso 1 de la validación, no por el 2: el `alg` no se negocia.»

### 5.d Token vencido → `401 TOKEN_EXPIRED`

```bash
docker compose exec -T -e ANA_ID="$ANA_ID" auth python - > /tmp/expired.txt <<'PY'
import os, time, uuid, jwt
key = open(os.environ["AUTH_JWT_PRIVATE_KEY_PATH"], "rb").read()
now = int(time.time())
claims = {
    "iss": os.environ["AUTH_JWT_ISSUER"],
    "sub": os.environ["ANA_ID"],
    "aud": [a.strip() for a in os.environ["AUTH_AUDIENCES"].split(",")],
    "iat": now - 2000,
    "exp": now - 1000,
    "jti": str(uuid.uuid4()),
    "token_use": "access",
    "username": "ana.perez",
}
print(jwt.encode(claims, key, algorithm="RS256", headers={"kid": os.environ["AUTH_JWT_KID"]}))
PY
EXPIRED_TOKEN=$(tail -1 /tmp/expired.txt)
call -X POST "$STEGO/steganography/analyze" -H "Authorization: Bearer $EXPIRED_TOKEN" \
  -F "file=@samples/sample-clean.png"
```

**Decir:** «Este token lo firmé con la clave real de AUTH: la firma es válida y aun así se rechaza, porque
`exp` está en el pasado. El único defecto es la vigencia, y lo corta el paso 6 de la validación. Es una
prueba más fuerte que un token mal firmado: demuestra que la expiración se comprueba de verdad.»

### 5.e Usuario sin privilegios → `403 FORBIDDEN`

```bash
LUIS_TOKEN=$(curl -s -X POST "$AUTH/auth/login" -H 'Content-Type: application/json' \
  -d "{\"identifier\":\"luis.vega\",\"password\":\"$LUIS_PASS\"}" | jq -r .access_token)

call -X POST "$STEGO/steganography/analyze" -H "Authorization: Bearer $LUIS_TOKEN" \
  -F "file=@samples/sample-clean.png"
```

**Decir:**

> «Luis está autenticado: el token es válido y su usuario está activo. Recibe `403`, no `401`, porque sé
> quién es y sé que no puede. AUTH devolvió `allowed: false` con `reason: no_active_role_for_action`:
> ningún rol activo suyo concede `steganography.analyze`. La matriz de permisos dice que USER solo alcanza
> su perfil y sus propios resultados; analizar exige ADMIN o ANALYST.»

**Mostrar:** el `403` de luis y, en el log de AUTH, la línea de decisión con `reason` (`docker compose logs
--tail=5 auth`).

**Plan B:**
- Si el token manipulado devuelve `200`: **es un defecto crítico**. No seguir como si nada: decir en voz
  alta «esto no debería pasar», anotarlo, ejecutar igualmente 5.c y 5.d para acotar el fallo y reportarlo al
  equipo al terminar; probablemente la verificación de firma está desactivada.
- Si el token vencido devuelve `200`: igual de grave, y suele significar que se valida con `verify_exp=False`.
- Si luis recibe `200`: su rol no es solo USER. Comprobar con la consulta del paso 2; si tiene ANALYST, la
  asignación del paso 2 usó el `role_id` equivocado.
- Si `PyJWT` no está disponible dentro del contenedor, plan B para el caso vencido: hacer `logout` y
  reutilizar el token (`401 TOKEN_REVOKED`), que también es un `401` legítimo, y explicar la diferencia.
- Si el tiempo aprieta: ejecutar 5.a, 5.b y 5.e. Son los tres que el enunciado nombra explícitamente
  (sin token, inválido, sin privilegios).

---

## 9. Paso 6 — Retirar el rol y reutilizar el JWT todavía vigente (1:30)

**Ejecutar (T2). El id de la asignación lo devolvió el `201` del paso 1:**

```bash
echo "asignación ANALYST de ana = $UR_ANALYST"
```

> `POST /api/v1/user-roles` responde `UserRoleOut` con `id`, `user_id`, `role_id`, `status` y `assigned_at`;
> ese `id` es el que consume `DELETE /api/v1/user-roles/:id`. Si la variable se perdió (se cerró la
> terminal), se recupera de la base: `docker compose exec -T db psql -U auth_app -d auth -tAc "SELECT id FROM
> auth.user_roles WHERE user_id = '$ANA_ID' AND role_id = '$ANALYST_ID'"`.

**Comprobar que el token sigue vivo y retirar el rol:**

```bash
python3 -c "import base64,json,os,time;p=os.environ['ANA_TOKEN'].split('.')[1];p+='='*(-len(p)%4);c=json.loads(base64.urlsafe_b64decode(p));print('quedan', c['exp']-int(time.time()), 's de vigencia')"

call -X DELETE "$AUTH/user-roles/$UR_ANALYST" -H "Authorization: Bearer $ADMIN_TOKEN"

# El MISMO token, sin volver a hacer login
call -X POST "$STEGO/steganography/analyze" -H "Authorization: Bearer $ANA_TOKEN" \
  -F "file=@samples/sample-clean.png"
```

**Segunda vía, desactivar sin borrar (30 s si el tiempo lo permite):**

Tras el `DELETE` la fila ya no existe; para demostrar la variante hay que crear una asignación nueva,
desactivarla y comprobar el `reason`:

```bash
NEW_UR=$(curl -s -X POST "$AUTH/user-roles" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"user_id\":\"$ANA_ID\",\"role_id\":\"$ANALYST_ID\"}" | jq -r .id)

call -X PATCH "$AUTH/user-roles/$NEW_UR" -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' -d '{"status":"inactive"}'

call -X POST "$STEGO/steganography/analyze" -H "Authorization: Bearer $ANA_TOKEN" \
  -F "file=@samples/sample-clean.png"
```

**Decir:**

> «El token de ana sigue siendo criptográficamente válido: acabo de imprimir cuántos segundos le quedan. No
> he vuelto a hacer login. Y aun así el análisis se deniega con `403`, porque AUTH releyó las asignaciones
> en esta petición y ya no existe la que concedía el permiso. En la segunda vía no la borro, la desactivo:
> el `403` llega igual y el registro histórico se conserva, que es lo que hace auditable una revocación.
> Esto es exactamente lo que no podría hacer un sistema que autorizara con los roles del token.»

**Mostrar:** los segundos restantes del token (deben ser > 0), el `204` del `DELETE`, el `403` inmediato con
el mismo token y la línea del log con `reason: assignment_missing` (o `assignment_inactive`). En T1, con el
nombre de usuario en lugar del id, para que la consulta funcione en esa terminal:

```bash
docker compose exec -T db psql -U auth_app -d auth -c "
SELECT u.username, r.name, ur.status, ur.id
FROM auth.user_roles ur
JOIN auth.users u ON u.id = ur.user_id
JOIN auth.roles r ON r.id = ur.role_id
WHERE u.username = 'ana.perez' ORDER BY r.name;"
```

**Plan B:**
- `404 ASSIGNMENT_NOT_FOUND` en el `DELETE`: `$UR_ANALYST` salió vacío o la asignación ya no existía del
  ensayo. Recuperar el id de la base (nota de arriba) y reintentar.
- Si el análisis sigue devolviendo `201` tras el `DELETE`: **defecto crítico de T07** —la autorización está
  usando datos cacheados o el token—. Decirlo, comprobar en el log de AUTH el `reason` y continuar con el paso 7.
- Si el `DELETE` devuelve `403` con el token de admin, el token caducó: renovarlo con el login del paso 1.
- Si no da tiempo a la segunda vía, decirla en una frase y mostrar el `reason` de la primera: la rúbrica
  pide la revocación, no las dos variantes.

---

## 10. Paso 7 — AUTH caído: `503` y fallo cerrado (1:00)

**Ejecutar (T1):**

```bash
# Estado de la tabla de análisis antes de la prueba (base stego, usuario stego_app)
docker compose exec -T db psql -U stego_app -d stego -tAc "SELECT count(*) FROM stego.analyses"

docker compose stop auth
sleep 2
curl -s -o /dev/null -w 'AUTH detenido: %{http_code}\n' http://localhost:8080/health || true
```

> La tabla vive en la base `stego` y se consulta con `stego_app`. Si se quiere dejar constancia del
> aislamiento, agregar `docker compose exec -T db psql -U auth_app -d stego -c "select 1"`, que debe fallar:
> `auth_app` no puede conectarse a la base del otro servicio.

**Ejecutar (T2) con un token válido:**

```bash
time call -X POST "$STEGO/steganography/analyze" -H "Authorization: Bearer $ANA_TOKEN" \
  -F "file=@samples/sample-clean.png"
```

**Comprobar que no se creó nada (T1):**

```bash
docker compose exec -T db psql -U stego_app -d stego -c "SELECT count(*) FROM stego.analyses;"
docker compose start auth && sleep 3
curl -s -o /dev/null -w 'AUTH de vuelta: %{http_code}\n' http://localhost:8080/health
```

**Decir:**

> «AUTH está detenido. STEGO verifica el token localmente sin problema, porque tiene la clave pública en
> caché, pero no puede obtener la decisión de autorización: prefiere denegar con `503` antes que procesar un
> archivo sin autorización comprobada. El contador de análisis no cambió: no se analizó, no se guardó el
> archivo y no se creó registro. Es denegación por defecto: un fallo de comunicación no se interpreta como
> permiso.»

**Mostrar:** el `503 AUTHORIZATION_UNAVAILABLE`, el tiempo de respuesta cercano al presupuesto de 2000 ms o
menor (conexión rechazada), el contador igual antes y después, y AUTH de vuelta con `200`.

**Plan B:**
- `401` en lugar de `503`: el token de ana caducó durante la demo. Repetir el análisis con un token nuevo
  **después** de devolver AUTH a `running`; si el `401` aparece con token fresco, STEGO está confundiendo un
  fallo de autorización con un token inválido, y eso es un hallazgo que hay que decir.
- `201` con AUTH detenido: **fail-open**, el peor resultado posible en esta demostración. Decirlo sin
  adornos, anotarlo y continuar.
- Si `docker compose stop auth` tarda o el `sleep` es insuficiente, esperar a que `/health` deje de responder.
- Si no arranca de vuelta, `docker compose up -d auth` y esperar el `healthcheck` (10–15 s). Mientras tanto,
  el paso 8 no puede ejecutarse: es la dependencia real del sistema y se puede decir como cierre.

---

## 11. Paso 8 — Imagen limpia frente a imagen con carga LSB (2:00)

**Ejecutar (T2). Primero, recuperar el permiso sin emitir token nuevo:**

```bash
# Si se ejecutó la segunda vía del paso 6, $NEW_UR es la asignación desactivada: se reactiva.
# Si se ejecutó solo el DELETE, no hay fila: se crea de nuevo. El efecto observable es el mismo.
if [ -n "${NEW_UR:-}" ]; then
  call -X PATCH "$AUTH/user-roles/$NEW_UR" -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H 'Content-Type: application/json' -d '{"status":"active"}'
else
  call -X POST "$AUTH/user-roles" -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "{\"user_id\":\"$ANA_ID\",\"role_id\":\"$ANALYST_ID\"}"
fi
```

> Reactivar concede el permiso en la siguiente petición sin emitir un token nuevo: la misma propiedad que se
> demostró al revocarlo, en sentido contrario. Si `$NEW_UR` se perdió, el `id` se recupera de la base:
> `docker compose exec -T db psql -U auth_app -d auth -tAc "SELECT id FROM auth.user_roles WHERE user_id =
> '$ANA_ID' AND status = 'inactive'"`.

**Analizar las dos muestras con el mismo token de ana:**

```bash
post_analyze() {   # $1 = muestra, $2 = archivo donde guardar el JSON
  local code
  code=$(curl -sS -o "$2" -w '%{http_code}' -X POST "$STEGO/steganography/analyze" \
    -H "Authorization: Bearer $ANA_TOKEN" -F "file=@$1")
  echo "HTTP $code  ←  $1"
  jq -c '{filename, status, action, sha256, indicators}' "$2"
}

post_analyze samples/sample-clean.png /tmp/clean.json
post_analyze samples/sample-lsb.png   /tmp/lsb.json
```

**Comparar, y contrastar el `sha256` con el calculado fuera del servicio (T1 o T2):**

```bash
jq -r '"\(.filename)\t\(.status)\t\(.action)\tanomaly=\(.indicators.anomaly_score)\tumbral=\(.indicators.threshold)\tp=\(.indicators.chi_square_pvalue)\tratio=\(.indicators.lsb_ones_ratio)"' \
  /tmp/clean.json /tmp/lsb.json
sha256sum samples/sample-clean.png samples/sample-lsb.png
```

**Decir:**

> «Las dos imágenes son la misma fotografía. La primera no tiene nada oculto; la segunda lleva un mensaje
> insertado por sustitución del bit menos significativo. En una imagen natural las frecuencias de cada par
> de valores `2k` y `2k+1` no son iguales; al sustituir el LSB se igualan, y la prueba de chi-cuadrado mide
> esa igualación.
>
> El `anomaly_score` es el máximo de dos indicadores: el p-valor del canal más sospechoso —cerca de cero en
> una imagen natural, cerca de uno cuando el plano LSB parece aleatorizado— y la tasa de sustitución
> estimada recorriendo prefijos de la imagen, que es la que estima qué proporción quedó sustituida. Con el
> umbral de 0,75, la muestra cargada cae en `sospechosos` y va a cuarentena; la limpia queda en
> `sin_indicios` sin acción.»
>
> «Dos precisiones honestas: `sospechosos` es un **indicio**, no una prueba de que haya un mensaje —el
> detector no extrae nada ni conoce la clave—; y el umbral de 0,75 es un valor inicial que todavía hay que
> calibrar con el conjunto de muestras, así que no afirmo una tasa de acierto que no he medido.»

**Mostrar:** las dos respuestas completas con `status`, `action`, `indicators` y `limitations`; los dos
`sha256` idénticos a los del host; y el `201` del análisis con carga.

**Bonus de 30 s si sobra tiempo (T11):**

```bash
call "$STEGO/steganography/results/$AID" -H "Authorization: Bearer $LUIS_TOKEN"
```

**Decir:** «Luis tiene rol USER, así que `results.read` sí está en su matriz; pero este análisis es de ana y
no es ADMIN. `403 RESULT_FORBIDDEN`: la decisión de rol la tomó AUTH y la propiedad del recurso la aplica
STEGO, que es la única regla de negocio que evalúa por sí mismo.»

**Plan B:**
- Si las dos muestras dan el mismo `status`: es el riesgo declarado del umbral sin calibrar (limitación S-1).
  Mostrar `indicators` de ambas, señalar la diferencia de `anomaly_score` y `estimated_embedding_rate`, y
  explicar la calibración pendiente. Tener preparada una segunda pareja de muestras con carga mayor (por
  ejemplo 100 % de la capacidad) y probarla.
- Si la cargada da `no_concluyentes`: leer `pair_bins_retained`, `pixels_analysed` y `distinct_values` en
  la respuesta y explicar la guarda que se disparó (imagen pequeña, paleta reducida o indicadores
  contradictorios). Es una respuesta correcta del sistema, no un fallo; decirlo así.
- Si el `anomaly_score` de la limpia y el de la cargada son parecidos: comparar también
  `estimated_embedding_rate` y `chi_square_pvalue` por separado, que es lo que realmente distingue a las
  dos muestras, y explicar que el máximo de ambos se queda corto cuando ninguno supera el umbral.
- Si la limpia da `sospechosos`: falso positivo. Explicarlo con S-2 (imágenes sintéticas de alta entropía)
  y mostrar el resto de indicadores.
- Si el `PATCH` de reactivación devuelve `404`: no hay fila inactiva (se usó `DELETE`). Crear la asignación
  con `POST` y continuar.
- Si los dos análisis dan `503`: AUTH no volvió del paso 7. `docker compose up -d auth`, esperar y repetir.

---

## 12. Cierre (30 s)

**Decir, sin leer:**

> «Quedan demostrados los dos servicios por separado, la relación N:M persistida con sus restricciones, el
> JWT firmado sin roles, la autorización resuelta contra la base en cada operación, las denegaciones 401 y
> 403, la revocación efectiva con el token aún vigente y el fallo cerrado cuando AUTH no puede decidir.
>
> Lo que no afirmo: el detector no prueba la existencia de un mensaje oculto, el umbral está sin calibrar,
> no hay TLS ni mTLS en esta versión y no alegamos certificación ISO ni cumplimiento integral de ninguna
> norma. Esas limitaciones están escritas en el documento técnico, sección 13, con su impacto y su plan de
> mitigación.»

Cerrar con la frase que el evaluador espera oír: **el sistema deniega por defecto y no autoriza con datos
del token.**

---

## 13. Versión de 8 minutos

Si el docente recorta el tiempo, se mantiene el orden y se recortan los tiempos, no los pasos:

| Paso | Versión de 8 min | Qué se omite |
|---|---|---|
| 0 | 0:00–0:20 | El `stop stego`; se muestra `compose ps` y se afirma T01 |
| 1 | 0:20–1:40 | Nada: es el paso que más pesa (T05) |
| 2 | 1:40–2:20 | La consulta agregada; basta el `201` y una fila |
| 3 | 2:20–2:50 | El perfil; basta el payload decodificado |
| 4 | 2:50–3:40 | Nada |
| 5 | 3:40–5:10 | `alg: none` y la segunda vía de revocación |
| 6 | 5:10–6:20 | La variante `PATCH status=inactive` |
| 7 | 6:20–7:00 | El contador de filas se muestra, no se recalcula |
| 8 | 7:00–8:00 | El bonus de T11 |

---

## 14. Preguntas probables y respuestas de dos líneas

| Pregunta | Respuesta |
|---|---|
| ¿Por qué el JWT no lleva roles? | Porque un token es un dato del pasado: si los roles viajan dentro, una revocación tarda hasta 900 s en surtir efecto. La autorización se resuelve contra la base en cada operación. |
| ¿Qué pasa si roban un token? | Sirve hasta 900 s o hasta `logout`; el `jti` se inserta en `revoked_tokens` y deja de valer. Además, si se desactiva el usuario o se retira el rol, la siguiente operación se deniega aunque el token siga vigente. |
| ¿Por qué RS256 y no HS256? | Con HS256, STEGO necesitaría la clave que firma, y el enunciado prohíbe que la reciba. Con RS256 solo tiene material público: puede verificar, no emitir. |
| ¿Cómo rotan la clave? | Se publica un `kid` nuevo en JWKS, se empieza a firmar con él y el anterior se retira cuando expiran los tokens emitidos con él. STEGO no se redespliega. |
| ¿Por qué una consulta de autorización por petición y no una caché? | Porque el requisito es que la revocación sea inmediata. El costo es una consulta y una llamada interna con presupuesto de 2000 ms; la decisión no se cachea ni se reutiliza. |
| ¿Qué pasa si AUTH se cae? | STEGO responde `503 AUTHORIZATION_UNAVAILABLE` y no procesa el archivo. Se prefiere denegar a procesar sin decisión; el costo es de disponibilidad y está declarado como riesgo R-08. |
| ¿Detecta toda la esteganografía? | No. Detecta la firma estadística de la sustitución LSB en PNG y BMP. Es ciego a LSB matching, a planos superiores y a formatos con pérdida; y `sin_indicios` no prueba ausencia de mensaje. |
| ¿Ese `0,82` es una medición? | Es un valor de ejemplo del contrato. La medición real va en los JSON de evidencia y el umbral está pendiente de calibración con la curva ROC de las muestras. |
| ¿Cumplen ISO 27001? | No. Se usan 27001 y 27034 como referencia de principios y de estructura de controles; no hay auditoría ni declaración de conformidad. |
| ¿Por qué no mTLS? | Es una mejora documentada (D-007): se priorizó el token de servicio sobre la red interna. mTLS exige CA, certificados y montajes que no cabían en el plazo; queda como trabajo siguiente. |
| ¿Por qué una sola base de datos? | Una instancia con dos bases y dos usuarios sin acceso cruzado cumple el aislamiento exigido sin levantar dos motores. La separación se verifica desde `psql`. |
| ¿Dónde está el código del analizador? | En STEGO, módulo de análisis; el diseño y las fórmulas están en la sección 7 del documento técnico. `⟨PENDIENTE · A08⟩` si aún no está cerrado. |

---

## 15. Frases prohibidas

- «Detecta esteganografía con un 99 % de precisión.» No hay medición; el umbral no está calibrado.
- «Cumplimos ISO/IEC 27001.» Se usa como referencia, no hay certificación.
- «Es seguro porque usa JWT.» El token identifica; la seguridad está en la decisión por operación.
- «El rol viene en el token.» Es exactamente lo que el diseño evita: nunca.
- «Si AUTH falla, sigue funcionando.» Falla cerrado: deja de analizar. Es una decisión, no un olvido.
- «Los tests pasan todos.» Se muestran los que se ejecutan; si alguno falla, se dice y se explica.

---

## 16. Plan de contingencia global

| Falla | Qué hacer | Qué decir |
|---|---|---|
| No arranca nada | `docker compose down -v && docker compose up -d --build`, 90 s | «Reaprovisiono el entorno; el arranque es reproducible con un comando.» |
| Un servicio queda `unhealthy` | `docker compose logs --tail=50 <svc>`; revisar `check-env.sh` y las claves | «Es un fallo de configuración, no de la demo; lo corrijo en un minuto.» |
| No hay red en el aula | Todo es local: no se necesita red salvo el `docker build`. Construir las imágenes antes de entrar | — |
| El proyector no muestra el color de `jq` | `jq -C .` no es necesario; el código HTTP se imprime aparte | — |
| Un endpoint todavía no implementado (A04–A08 abiertos) | Mostrar el contrato, el JSON Schema y la evidencia de `evidence/` si existe; decir qué falta | «El contrato está congelado y la implementación está en curso; la evidencia disponible es esta.» |
| Se cae la demo entera | Cambiar a la presentación del documento: arquitectura, matriz y limitaciones. La rúbrica también evalúa diseño y documentación | «Paso al diseño, que es lo que puedo demostrar sin entorno.» |

**Regla de oro para los planes B:** nunca inventar una salida. Si algo no funciona, se dice qué se esperaba,
qué se obtuvo y por qué. Un fallo explicado con precisión vale más que una captura que no se puede
reproducir, y el enunciado prohíbe expresamente reemplazar la ejecución por capturas.

---

## Anexo. Evidencias que hay que guardar durante la defensa

| Paso | Archivo sugerido | Qué debe contener |
|---|---|---|
| 0 | `evidence/T01/compose-ps.txt` | Tres servicios, los dos `/health` |
| 1 | `evidence/T05/ana-dos-roles.txt` | Dos `201` y la consulta con dos filas |
| 2 | `evidence/T05/rol-dos-usuarios.txt` | `201` y el agregado: rol USER, 2 usuarios |
| 3 | `evidence/T02/login-y-claims.txt` | Payload sin roles, `exp - iat = 900` |
| 4 | `evidence/T09/analyze-clean-primera.txt` | `201` con `sha256` e `indicators` |
| 5 | `evidence/T03/401-sin-token.txt`, `T03/401-manipulado.txt`, `T03/401-vencido.txt`, `T04/403-user.txt` | Código HTTP y cuerpo |
| 6 | `evidence/T07/revocacion-mismo-jwt.txt` | Segundos restantes, `204`, `403`, `reason` |
| 7 | `evidence/T08/auth-caido-503.txt` | `503`, contadores antes y después |
| 8 | `evidence/T09/clean-vs-lsb.txt` | Los dos JSON y los `sha256sum` |

Todo archivo de evidencia se guarda sin secretos: ni contraseñas, ni tokens completos, ni claves. Si un log
contiene un token, se recorta y se indica el recorte.
