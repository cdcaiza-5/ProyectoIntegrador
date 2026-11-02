# Contrato 7 — Puertos, variables de entorno, rutas y convenciones

**Estado:** CONGELADO v1.3.0 · **Dueño:** DevOps / integración

**Cambios v1.3.0:** la plantilla de entorno pasa a llamarse `.env.example`, que es el nombre que exige el enunciado (§3).

**Cambios v1.1.0:** se adoptan las convenciones del repositorio de referencia del curso
([`agcudco/product-service-fast-api`](https://github.com/agcudco/product-service-fast-api)):
prefijo `/api/v1`, variables `DB_*`, plantilla `.env.example` y paginación con `limit`.
El JSON sigue en `snake_case` para no invalidar los esquemas de `contracts/`.

Estos nombres son contrato: aparecen en `docker-compose.yml`, en los dos `.env.example` y en el
README. Cambiar uno obliga a cambiar los tres y avisar a ambos servicios.

---

## 1. Servicios, puertos y URLs

| Servicio Compose | Nombre interno | Puerto interno | Publicado en host | URL desde el host | URL entre contenedores |
|---|---|---|---|---|---|
| `auth` | AUTH | 8080 | 8080 | `http://localhost:8080` | `http://auth:8080` |
| `stego` | STEGO | 8081 | 8081 | `http://localhost:8081` | `http://stego:8081` |
| `db` | PostgreSQL 16 | 5432 | **no publicado** | — | `postgresql://db:5432` |
| volumen | `stego_storage` | — | — | — | `/var/stego` dentro de `stego` |

- Inspección de la base: `docker compose exec db psql -U auth_app -d auth` (no se publica el puerto).
- Bases separadas con usuarios distintos: `auth` / `auth_app` y `stego` / `stego_app`.
  `auth_app` no tiene privilegios sobre la base `stego` y viceversa.
- Redes:
  - `backend_net` (`internal: true`) → comunicación AUTH↔STEGO y ambas con `db`.
  - `edge_net` (bridge normal) → solo `auth` y `stego`, para publicar los puertos de la demostración.
  - `db` se conecta únicamente a `backend_net`.

Nombres canónicos para documentación y diagramas: **AUTH** y **STEGO**.

---

## 2. Variables de AUTH

| Variable | Obligatoria | Ejemplo / valor por defecto | Nota |
|---|---|---|---|
| `AUTH_HTTP_PORT` | sí | `8080` | |
| `DB_HOST` | sí | `db` | Estilo del curso; `DATABASE_URL` se arma en `Settings` |
| `DB_PORT` | sí | `5432` | |
| `DB_NAME` | sí | `auth` | Base exclusiva de AUTH |
| `DB_USER` | sí | `auth_app` | Sin privilegios sobre la base `stego` |
| `DB_PASSWORD` | sí | `<cambiar>` | No se versiona |
| `AUTH_JWT_PRIVATE_KEY_PATH` | sí | `/run/secrets/jwt_private.pem` | **Solo AUTH** |
| `AUTH_JWT_PUBLIC_KEY_PATH` | sí | `/run/secrets/jwt_public.pem` | Se publica por JWKS |
| `AUTH_JWT_KID` | sí | `auth-2026-11` | Debe aparecer en el header de los JWKS |
| `AUTH_JWT_ISSUER` | sí | `auth-service` | Igual en ambos servicios |
| `AUTH_ACCESS_TOKEN_TTL_SECONDS` | sí | `900` | 15 min |
| `AUTH_AUDIENCES` | sí | `auth-api,stego-api` | Lista separada por comas |
| `AUTH_SERVICE_TOKEN_TTL_SECONDS` | sí | `300` | Token de servicio |
| `AUTH_SERVICE_CLIENT_ID` | sí | `stego` | Cliente autorizado |
| `AUTH_SERVICE_CLIENT_SECRET` | sí | `<secreto>` | Solo se guarda su hash Argon2id |
| `AUTH_AUTHZ_DECISION_TTL_SECONDS` | sí | `30` | `decision_ttl_seconds` de la respuesta |
| `AUTH_LOGIN_RATE_LIMIT_PER_MINUTE` | sí | `5` | Por IP + identificador; bloqueo de 60 s al exceder |
| `AUTH_LOG_LEVEL` | no | `info` | `debug`/`info`/`warn`/`error` |

## 3. Variables de STEGO

| Variable | Obligatoria | Ejemplo / valor por defecto | Nota |
|---|---|---|---|
| `STEGO_HTTP_PORT` | sí | `8081` | |
| `DB_HOST` | sí | `db` | Mismo estilo que AUTH |
| `DB_PORT` | sí | `5432` | |
| `DB_NAME` | sí | `stego` | Base exclusiva de STEGO |
| `DB_USER` | sí | `stego_app` | Sin privilegios sobre la base `auth` |
| `DB_PASSWORD` | sí | `<cambiar>` | No se versiona |
| `STEGO_AUTH_BASE_URL` | sí | `http://auth:8080` | Base para `/internal/*` |
| `STEGO_AUTH_JWKS_URL` | sí | `http://auth:8080/.well-known/jwks.json` | |
| `STEGO_AUTH_JWKS_TIMEOUT_MS` | sí | `1500` | |
| `STEGO_SERVICE_CLIENT_ID` | sí | `stego` | |
| `STEGO_SERVICE_CLIENT_SECRET` | sí | `<secreto>` | Debe coincidir con AUTH |
| `STEGO_SERVICE_TOKEN_REFRESH_SECONDS` | sí | `240` | Renovar antes de que expiren los 300 s |
| `STEGO_AUTHZ_TIMEOUT_MS` | sí | `2000` | Presupuesto total de la decisión |
| `STEGO_MAX_UPLOAD_BYTES` | sí | `5242880` | 5 MiB |
| `STEGO_ALLOWED_EXTENSIONS` | sí | `png,bmp` | Lista blanca |
| `STEGO_ALLOWED_CONTENT_TYPES` | sí | `image/png,image/bmp,image/x-ms-bmp` | Lista blanca |
| `STEGO_MAX_IMAGE_DIMENSION` | sí | `10000` | px por lado |
| `STEGO_MAX_IMAGE_PIXELS` | sí | `25000000` | |
| `STEGO_LSB_ANOMALY_THRESHOLD` | sí | `0.75` | Calibrar con muestras y documentarlo |
| `STEGO_STORAGE_QUARANTINE_PATH` | sí | `/var/stego/quarantine` | Volumen, no público |
| `STEGO_STORAGE_RETENTION_DAYS` | no | `7` | Informativo para la política |
| `STEGO_LOG_LEVEL` | no | `info` | |

---

## 4. Rutas

| Qué | Ruta | Quién |
|---|---|---|
| Claves JWT (fuera del repo) | `.secrets/jwt_private.pem`, `.secrets/jwt_public.pem` | Solo AUTH lee la privada |
| Secretos local | `.env` (ignorado por git) | Compose |
| Plantillas | `auth/.env.example`, `stego/.env.example` | Sin secretos reales |
| Migraciones | `db/auth/001_init.sql`, `db/stego/001_init.sql` | Aprovisionamiento |
| Cuarentena de archivos | `/var/stego/quarantine` (volumen `stego_storage`) | Solo STEGO |
| Evidencias de pruebas | `evidence/` (capturas, salidas, colección Postman) | Equipo |
| Muestras | `samples/` (`sample-clean.png`, `sample-lsb.png`, …) | Equipo |

`.gitignore` mínimo obligatorio: `.env`, `.secrets/`, `evidence/raw/`, `samples/generated/`,
`__pycache__/`, `node_modules/`, `dist/`, `*.log`.

---

## 5. Convenciones transversales de API

| Convención | Valor |
|---|---|
| Codificación | JSON UTF-8, `Content-Type: application/json` (salvo multipart en analyze) |
| Nombres de campos | `snake_case` |
| Fechas | ISO-8601 UTC con sufijo `Z` (`2026-11-02T19:40:00Z`) |
| Identificadores | UUID v4 |
| Trazabilidad | `X-Request-Id`: se acepta solo si cumple `^[A-Za-z0-9._-]{1,64}$`; si no, se genera. STEGO la propaga a AUTH |
| Paginación | `?page` (≥1) y `?limit` (1–100, por defecto 20) con `{"items": [...], "page": 1, "limit": 20, "total": 0}` |
| Versión de API | Prefijo `/api/v1` en todos los endpoints públicos, configurable con `API_V1_STR` |
| Errores | Envoltorio único (§6) |
| Health | `GET /health` en ambos, público, sin secretos: `{"status":"ok","service":"auth"}` |

### Rutas excluidas del prefijo

Salen literalmente del enunciado y **no** llevan `/api/v1`:

| Ruta | Motivo |
|---|---|
| `POST /internal/authorization/check` | El enunciado la nombra así y debe ser identificable como interna |
| `POST /internal/service-token` | Consistencia con la anterior |
| `GET /.well-known/jwks.json` | Ruta convencional de descubrimiento |
| `GET /health` | Convención de salud, sin versión |

### Cómo conviven los `DB_*` de ambos servicios

Los dos servicios usan los mismos nombres (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`)
porque cada uno tiene su propio archivo de entorno. **No** se comparte un `.env` raíz entre servicios:

```
auth/.env          → DB_NAME=auth,   DB_USER=auth_app
stego/.env         → DB_NAME=stego,  DB_USER=stego_app
```

En `docker-compose.yml` cada servicio carga el suyo:

```yaml
services:
  auth:
    env_file: ./auth/.env
  stego:
    env_file: ./stego/.env
```

Las credenciales que **crea** el contenedor de PostgreSQL viven en un `.env` raíz distinto, usado solo
para la interpolación de Compose (`AUTH_DB_PASSWORD`, `STEGO_DB_PASSWORD`) y para el script de
`docker-entrypoint-initdb.d` que crea ambas bases. Ese archivo nunca se monta dentro de los servicios.

### Envoltorio de error (único en ambos servicios)

```json
{
  "error": {
    "code": "TOKEN_INVALID",
    "message": "El token no es válido.",
    "details": [{ "field": "authorization", "issue": "signature_mismatch" }],
    "request_id": "8f1c2a9e-5b7d-4c8e-9a10-7d6f5e4b3c21",
    "timestamp": "2026-11-02T19:40:00Z"
  }
}
```

`code` es estable y probado; `message` es para humanos y puede cambiar. `details` es opcional.
Nunca se devuelven stack traces, rutas de archivo internas, SQL ni trazas de librería.

---

## 6. Catálogo de códigos de error

| Código | HTTP típico | Servicio |
|---|---|---|
| `VALIDATION_ERROR` | 422 | ambos |
| `TOKEN_MISSING` | 401 | ambos |
| `TOKEN_INVALID` | 401 | ambos |
| `TOKEN_EXPIRED` | 401 | ambos |
| `TOKEN_REVOKED` | 401 | ambos |
| `SUBJECT_INACTIVE` | 401 | AUTH / STEGO |
| `AUTH_INVALID_CREDENTIALS` | 401 | AUTH |
| `FORBIDDEN` | 403 | ambos |
| `RESULT_FORBIDDEN` | 403 | STEGO |
| `USER_NOT_FOUND` | 404 | AUTH |
| `ROLE_NOT_FOUND` | 404 | AUTH |
| `ASSIGNMENT_NOT_FOUND` | 404 | AUTH |
| `RESULT_NOT_FOUND` | 404 | STEGO |
| `USER_EXISTS` / `EMAIL_EXISTS` | 409 | AUTH |
| `ROLE_EXISTS` | 409 | AUTH |
| `ASSIGNMENT_EXISTS` | 409 | AUTH |
| `ROLE_IN_USE` | 409 | AUTH |
| `PAYLOAD_TOO_LARGE` | 413 | ambos |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | STEGO |
| `FILE_SIGNATURE_MISMATCH` | 415 | STEGO |
| `IMAGE_UNPROCESSABLE` | 422 | STEGO |
| `RATE_LIMITED` | 429 | ambos |
| `SERVICE_AUTH_FAILED` | 401 | AUTH |
| `AUTHORIZATION_UNAVAILABLE` | 503 | STEGO |
| `INTERNAL_ERROR` | 500 | ambos |

---

## 7. Aceptación

- [ ] `docker compose up` arranca `auth`, `stego` y `db` sin pasos manuales extra.
- [ ] Cada servicio puede detenerse y arrancar por separado sin afectar al otro (T01).
- [ ] Ambos `.env.example` existen, no contienen secretos reales y cubren todas las variables obligatorias.
- [ ] `GET http://localhost:8080/health` y `GET http://localhost:8081/health` responden `200`.
- [ ] `db` no está accesible desde el host en el puerto 5432.
- [ ] Ningún log ni respuesta contiene `password_hash`, claves, JWT completos ni cadenas de conexión.
- [ ] La base `auth` y la base `stego` se crean con usuarios distintos y sin permisos cruzados.
