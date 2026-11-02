# Contrato 2 y 3 — Autorización interna y autenticación servicio→servicio

**Estado:** CONGELADO v1.0.0 · **Servidor:** AUTH · **Cliente:** STEGO

---

## 1. Flujo

```
Cliente de pruebas
   │ 1. POST /api/v1/auth/login                      (AUTH)
   │ ◄── access token (RS256, 900 s)
   │
   │ 2. POST /api/v1/steganography/analyze   Authorization: Bearer <access token>   (STEGO)
   ▼
STEGO
   │ 3. verifica firma/claims con JWKS (contrato 1)          → si falla: 401, sin leer el archivo
   │ 4. obtiene token de servicio (client_credentials)        → si falla: 503, sin leer el archivo
   │ 5. POST /internal/authorization/check                    → si falla/timeout: 503, sin procesar
   │ ◄── decisión {allowed, roles, reason, ...}
   │ 6. si allowed=false → 401/403 según §5
   │ 7. valida el archivo, analiza, persiste y devuelve el resultado
   ▼
AUTH
   (revalida el token del usuario y lee usuarios/roles/asignaciones vigentes en la BD)
```

Reglas no negociables de STEGO:

- No consulta la base de datos de AUTH, en ningún caso, ni siquiera para leer roles.
- No almacena contraseñas ni recibe la clave privada de firma.
- No acepta permisos del cliente: se ignoran por completo las cabeceras y campos tipo
  `X-Role`, `X-User-Id`, `roles`, `isAdmin`, `permissions`.
- Sin decisión verificable **no se procesa** el archivo (ni se guarda en cuarentena).

---

## 2. Autenticación servicio→servicio (contrato 3)

| Elemento | Valor congelado |
|---|---|
| Esquema | OAuth2 `client_credentials` simplificado, implementado a mano |
| Endpoint de token | `POST /internal/service-token` en AUTH |
| Credenciales | `STEGO_SERVICE_CLIENT_ID` + `STEGO_SERVICE_CLIENT_SECRET` |
| Almacenamiento del secreto | AUTH guarda solo el **hash Argon2id** del secreto en `auth.service_clients` |
| Token de servicio | JWT `RS256`, `token_use: "service"`, `sub: "service:stego"`, `aud: ["auth-internal"]`, TTL **300 s** |
| Uso | `Authorization: Bearer <service token>` contra `/internal/authorization/check` |
| Caché en STEGO | Permitida; se renueva cuando queda < 60 s de vida |
| Transporte | Red interna de Docker (`backend_net`, `internal: true`); los puertos se publican solo para la demostración |
| Fuerza extra | mTLS queda como mejora opcional documentada; no es requisito para aprobar |

### `POST /internal/service-token`

Solicitud:

```json
{ "client_id": "stego", "client_secret": "<secreto>" }
```

Respuesta `200`:

```json
{ "access_token": "<jwt>", "token_type": "Bearer", "expires_in": 300 }
```

Fallos: `401 SERVICE_AUTH_FAILED` (credenciales inválidas o cliente inactivo), `429 RATE_LIMITED`,
`400 VALIDATION_ERROR`. Un token de **usuario** recibido en `/internal/*` se rechaza con
`401 SERVICE_AUTH_FAILED`: la audiencia y `token_use` son distintos a propósito.

---

## 3. `POST /internal/authorization/check`

Cabeceras:

| Cabecera | Obligatoria | Regla |
|---|---|---|
| `Authorization` | sí | `Bearer <service token>` |
| `Content-Type` | sí | `application/json` |
| `X-Request-Id` | sí | UUID v4; se propaga desde STEGO y se registra en ambos servicios |

Solicitud (esquema: `contracts/authz-check.request.schema.json`):

```json
{
  "subject_token": "<JWT_DEL_USUARIO_SIN_PREFIJO_BEARER>",
  "action": "steganography.analyze",
  "resource_id": null
}
```

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `subject_token` | string | sí | El JWT del usuario tal cual llegó (sin `Bearer `), máximo 4096 caracteres |
| `action` | string | sí | Uno de los valores de `03-matriz-permisos.md`; valor desconocido → `allowed: false` |
| `resource_id` | string UUID \| null | sí (puede ser `null`) | Recurso sobre el que se opera; `null` cuando no aplica |

Respuesta `200` (esquema: `contracts/authz-check.response.schema.json`):

```json
{
  "decision_id": "9a7b6c5d-4e3f-4a2b-8c1d-0e9f8a7b6c5d",
  "subject_id": "3f1c2a9e-5b7d-4c8e-9a10-7d6f5e4b3c21",
  "action": "steganography.analyze",
  "resource_id": null,
  "allowed": true,
  "reason": "active_role_grants_permission",
  "roles": ["ANALYST"],
  "decided_at": "2026-11-02T19:40:00Z",
  "decision_ttl_seconds": 30
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `decision_id` | UUID | Identificador de la decisión, para auditoría y trazabilidad |
| `subject_id` | UUID \| null | `sub` del token; `null` si el token es inválido |
| `action` | string | Eco de la acción solicitada |
| `resource_id` | UUID \| null | Eco del recurso |
| `allowed` | boolean | Decisión final de AUTH |
| `reason` | string (enum) | Motivo legible por máquina (§4) |
| `roles` | array de string | Roles **efectivos en el instante de la decisión** (puede ser `[]`) |
| `decided_at` | string ISO-8601 UTC | Momento de la decisión |
| `decision_ttl_seconds` | integer | 30; la decisión **no** se reutiliza |

Un `allowed: false` con HTTP `200` es una **decisión válida**, no un error. STEGO lo traduce al código
HTTP del §5. Todo lo que no sea `200` con JSON válido se trata como denegación por defecto.

### Prohibiciones del contrato

- STEGO **no** puede cachear decisiones ni reutilizar `decision_id` para otra operación.
- AUTH **no** puede devolver la decisión sin haber releído la BD en esa misma petición.
- La respuesta no contiene correo, nombre, `password_hash`, roles inactivos ni ninguna clave.

---

## 4. Catálogo de `reason`

| `reason` | `allowed` | Significado |
|---|---|---|
| `active_role_grants_permission` | true | Un rol activo y vigente concede la acción |
| `no_active_role_for_action` | false | El usuario existe y está activo, pero ningún rol vigente concede la acción |
| `user_inactive` | false | `users.status` ≠ `active` |
| `role_inactive` | false | El rol que concedería la acción está inactivo |
| `assignment_missing` | false | La asignación fue retirada (`DELETE`) |
| `assignment_inactive` | false | La asignación existe pero su `status` es `inactive` |
| `unknown_action` | false | `action` no pertenece al catálogo congelado |
| `token_invalid` | false | Firma, `iss`, `aud`, `typ`, `jti` o `sub` inválidos |
| `token_expired` | false | `exp` superado |
| `subject_not_found` | false | `sub` sin usuario asociado |

---

## 5. Traducción de la decisión a la respuesta al cliente (STEGO)

| Situación | HTTP | Código |
|---|---|---|
| Token ausente, malformado, firma o claims inválidos | `401` | `TOKEN_INVALID` |
| Token vencido o revocado | `401` | `TOKEN_EXPIRED` / `TOKEN_REVOKED` |
| Decisión `allowed:false` con `user_inactive` | `401` | `SUBJECT_INACTIVE` |
| Decisión `allowed:false` con `subject_not_found` o `token_invalid` | `401` | `TOKEN_INVALID` |
| Decisión `allowed:false` por falta de rol (`no_active_role_for_action`, `assignment_missing`, `assignment_inactive`, `role_inactive`, `unknown_action`) | `403` | `FORBIDDEN` |
| Recurso existente pero de otro usuario y el solicitante no es ADMIN | `403` | `RESULT_FORBIDDEN` |
| AUTH inaccesible, timeout, error 5xx, respuesta no parseable, token de servicio inválido | `503` | `AUTHORIZATION_UNAVAILABLE` |

`503 AUTHORIZATION_UNAVAILABLE` es el comportamiento de **fallo seguro** exigido (T08): no se analiza,
no se persiste el archivo, no se crea registro de análisis.

---

## 6. Tiempos y reintentos

| Parámetro | Valor | Regla |
|---|---|---|
| Timeout total de `authorization/check` | 2000 ms | Presupuesto completo, conexión + lectura |
| Reintentos | 0 | Un fallo de autorización no se reintenta: se deniega |
| Timeout de obtención de JWKS | 1500 ms | Si falla y no hay caché válida → `503` |
| `decision_ttl_seconds` | 30 | Informativo para auditoría; STEGO no lo usa como caché |
| Vida del token de servicio | 300 s | Renovación anticipada a los 240 s |

---

## 7. Auditoría (ambos lados)

Se registra una línea estructurada por decisión con: `request_id`, `decision_id`, `subject_id`,
`action`, `resource_id`, `allowed`, `reason`, `roles`, latencia en ms, servicio de origen.
Nunca se registra el token completo, el secreto del cliente, ni el `password_hash`. Del token se puede
registrar `jti` y los últimos 6 caracteres como máximo, si sirve para depuración.

---

## 8. Aceptación

- [ ] STEGO obtiene un token de servicio y lo reutiliza dentro de los 300 s.
- [ ] Un token de usuario enviado a `/internal/authorization/check` devuelve `401 SERVICE_AUTH_FAILED`.
- [ ] Sin token de servicio → `401 SERVICE_AUTH_FAILED`.
- [ ] `allowed:false` llega al cliente como `403` cuando falta rol (T04).
- [ ] Retirar una asignación (`DELETE`) cambia el resultado a `allowed:false` en la siguiente petición,
      con el mismo JWT aún vigente (T07).
- [ ] Desactivar una asignación (`status='inactive'`) produce el mismo efecto, con `reason:
      assignment_inactive` (T07, segunda vía).
- [ ] AUTH detenido → `503 AUTHORIZATION_UNAVAILABLE` y `stego.analyses` queda sin nuevas filas (T08).
- [ ] La respuesta incluye exactamente los 9 campos y ningún otro.
- [ ] La decisión se obtiene en < 2000 ms en condiciones normales.
