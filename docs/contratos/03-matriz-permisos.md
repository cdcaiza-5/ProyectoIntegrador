# Contrato 4 — Matriz de acciones, roles y endpoints

**Estado:** CONGELADO v1.0.0

La matriz es la **fuente única de verdad** de la autorización. Cualquier otro listado en código,
documentación o diapositivas debe derivarse de aquí. Los roles se leen de la base de datos vigente;
no existe ninguna lista de usuarios o permisos hardcodeada.

---

## 1. Roles

| Rol | Propósito | Regla de mínimo privilegio |
|---|---|---|
| `ADMIN` | Administración de identidades y operaciones privilegiadas | Único que crea/edita usuarios, roles y asignaciones |
| `ANALYST` | Análisis de imágenes y consulta de sus resultados | No administra identidades; no ve resultados ajenos |
| `USER` | Acceso al propio perfil | No analiza imágenes; solo consulta sus propios resultados |

Un usuario puede acumular roles; la decisión es la **unión** de permisos de los roles activos. Los
roles con `status = 'inactive'` se ignoran aunque la asignación exista.

---

## 2. Catálogo de acciones

| Acción | ADMIN | ANALYST | USER |
|---|:---:|:---:|:---:|
| `auth.profile.read` | ✓ | ✓ | ✓ |
| `auth.logout` | ✓ | ✓ | ✓ |
| `users.create` | ✓ | — | — |
| `users.list` | ✓ | — | — |
| `users.update` | ✓ | — | — |
| `roles.create` | ✓ | — | — |
| `roles.list` | ✓ | — | — |
| `roles.update` | ✓ | — | — |
| `user_roles.create` | ✓ | — | — |
| `user_roles.update` | ✓ | — | — |
| `user_roles.delete` | ✓ | — | — |
| `steganography.analyze` | ✓ | ✓ | — |
| `steganography.results.read` | ✓ | ✓ | ✓ |

La autorización exige **tres** condiciones simultáneas, todas leídas de la base de datos en el momento
de la decisión:

1. `users.status = 'active'`
2. `user_roles.status = 'active'` (la asignación no fue desactivada ni borrada)
3. `roles.status = 'active'`

Basta que una falle para que la decisión sea `allowed:false`.

`steganography.results.read` es la única acción con **restricción por recurso**: AUTH decide el nivel
de rol y STEGO aplica la propiedad (§3). Retirar el rol elimina el permiso en la siguiente petición.

---

## 3. Regla de propiedad de recursos (la aplica STEGO, no AUTH)

```
puede_leer = (allowed == true)                     // decisión de AUTH para steganography.results.read
             AND ( "ADMIN" ∈ roles                 // ADMIN ve cualquier análisis
                   OR analysis.user_id == subject_id )   // resto: solo lo propio
```

Esta es la única regla de negocio que STEGO evalúa por sí mismo. No inventa ni amplía permisos: solo
restringe el acceso a un resultado concreto. Si `resource_id` apunta a un análisis inexistente →
`404 RESULT_NOT_FOUND`; si existe y no cumple la propiedad → `403 RESULT_FORBIDDEN` (T11).

Para `steganography.analyze`, `resource_id` es `null`: la autorización es puramente de rol.

---

## 4. Mapeo endpoint → método HTTP → acción

### AUTH

| Método | Ruta | Acción / control | Códigos esperados |
|---|---|---|---|
| POST | `/api/v1/auth/login` | Público + tasa limitada (5/60 s) | `200`, `401 AUTH_INVALID_CREDENTIALS`, `422`, `429 RATE_LIMITED` |
| GET | `/api/v1/auth/profile` | `auth.profile.read` | `200`, `401`, `403` |
| POST | `/api/v1/auth/logout` | `auth.logout` | `204`, `401` |
| POST | `/api/v1/users` | `users.create` | `201`, `401`, `403`, `409`, `422` |
| GET | `/api/v1/users` | `users.list` | `200`, `401`, `403` |
| PATCH | `/api/v1/users/:id` | `users.update` | `200`, `401`, `403`, `404` |
| POST | `/api/v1/roles` | `roles.create` | `201`, `401`, `403`, `409`, `422` |
| GET | `/api/v1/roles` | `roles.list` | `200`, `401`, `403` |
| PATCH | `/api/v1/roles/:id` | `roles.update` | `200`, `401`, `403`, `404` |
| POST | `/api/v1/user-roles` | `user_roles.create` | `201`, `401`, `403`, `404`, `409` |
| PATCH | `/api/v1/user-roles/:id` | `user_roles.update` (activar/desactivar) | `200`, `401`, `403`, `404` |
| DELETE | `/api/v1/user-roles/:id` | `user_roles.delete` | `204`, `401`, `403`, `404` |
| POST | `/internal/authorization/check` | Solo servicio autenticado (contrato 2) | `200`, `400`, `401`, `429`, `500` |
| POST | `/internal/service-token` | Credenciales de cliente | `200`, `400`, `401`, `429` |
| GET | `/.well-known/jwks.json` | Público (solo clave pública) | `200` |
| GET | `/health` | Público, sin datos sensibles | `200` |

### STEGO

| Método | Ruta | Acción / control | Códigos esperados |
|---|---|---|---|
| POST | `/api/v1/steganography/analyze` | JWT + `steganography.analyze` | `201`, `401`, `403`, `413`, `415`, `422`, `503` |
| GET | `/api/v1/steganography/results/:id` | JWT + `steganography.results.read` + propiedad | `200`, `401`, `403`, `404`, `503` |
| GET | `/health` | Público, sin datos sensibles | `200` |

Las acciones de AUTH se resuelven **también** por la misma vía de decisión (usuario → roles vigentes en
BD), no por un middleware con lista fija. Es la forma de que la revocación funcione en todos los
endpoints y no solo en STEGO.

---

## 5. Reglas de denegación

| Caso | Código | Código de error | Nota |
|---|---|---|---|
| Sin cabecera `Authorization` | `401` | `TOKEN_MISSING` | |
| Token inválido, mal firmado, `alg` no permitido, `iss`/`aud` incorrectos | `401` | `TOKEN_INVALID` | |
| Token vencido | `401` | `TOKEN_EXPIRED` | |
| Token revocado por logout | `401` | `TOKEN_REVOKED` | |
| Usuario desactivado | `401` | `SUBJECT_INACTIVE` | |
| Autenticado sin el rol requerido | `403` | `FORBIDDEN` | |
| Recurso ajeno sin ser ADMIN | `403` | `RESULT_FORBIDDEN` | |
| AUTH no responde para autorizar | `503` | `AUTHORIZATION_UNAVAILABLE` | Fallo seguro |

`401` = no sé quién eres. `403` = sé quién eres, pero no puedes. No se mezclan.

---

## 6. Aceptación

- [ ] Las tres operaciones de T05 (dos roles a un usuario, un rol a dos usuarios) se autorizan como dice la matriz.
- [ ] `USER` recibe `403 FORBIDDEN` en `analyze` (T04).
- [ ] `ANALYST` no puede llamar a `/api/v1/users` (`403`).
- [ ] Un `ADMIN` sin rol `ANALYST` sí puede analizar (la matriz lo permite).
- [ ] Tras `DELETE /api/v1/user-roles/:id`, la siguiente llamada con el mismo JWT devuelve `403` (T07).
- [ ] Tras `PATCH /api/v1/user-roles/:id` con `status: inactive`, la siguiente llamada devuelve `403` y
      el registro histórico sigue existiendo (T07, segunda vía).
- [ ] La matriz documentada y el comportamiento real coinciden fila por fila (revisión manual en la defensa).
