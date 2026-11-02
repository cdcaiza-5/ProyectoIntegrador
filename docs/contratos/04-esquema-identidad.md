# Contrato 5 — Esquema de base de datos de identidad (AUTH)

**Estado:** CONGELADO v1.0.0 · **Motor:** PostgreSQL 16 · **Esquema:** `auth`
**Script ejecutable:** [`db/auth/001_init.sql`](../../db/auth/001_init.sql)

Esta base de datos pertenece **exclusivamente** a AUTH. STEGO no tiene credenciales, conexión ni
permiso de lectura sobre este esquema.

---

## 1. Diagrama

```
users (1) ──────< user_roles >────── (1) roles
   │                  │
   │                  ├── id (PK)
   │                  ├── user_id  (FK → users.id,      ON DELETE CASCADE)
   │                  ├── role_id  (FK → roles.id,      ON DELETE RESTRICT)
   │                  ├── assigned_at
   │                  ├── assigned_by (FK → users.id, nullable)
   │                  └── UNIQUE (user_id, role_id)

users      : id (PK) · username (único, sin distinguir mayúsculas) · email (único, idem)
             password_hash · status · created_at · updated_at
roles      : id (PK) · name (único, sin distinguir mayúsculas) · description · status · created_at · updated_at
user_roles : id (PK) · user_id (FK) · role_id (FK) · assigned_at · assigned_by · status · UNIQUE(user_id, role_id)
```

Tablas auxiliares del mismo esquema:

| Tabla | Para qué |
|---|---|
| `auth.revoked_tokens` | `jti` invalidados por `POST /api/v1/auth/logout` (contrato 1) |
| `auth.service_clients` | clientes de servicio con secreto hasheado (contrato 3) |

---

## 2. Ejecución

```bash
psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
     -v ON_ERROR_STOP=1 -f db/auth/001_init.sql
```

Debe correr sin errores sobre una base vacía, ser idempotente en la creación de objetos y sembrar los
roles `ADMIN`, `ANALYST`, `USER` sin duplicarlos si se ejecuta dos veces.

---

## 3. Reglas de integridad que la aplicación debe respetar

| Regla | Dónde se impone | Efecto observable |
|---|---|---|
| `username` y `email` únicos sin distinguir mayúsculas | índice único sobre `lower(...)` | `409 USER_EXISTS` / `409 EMAIL_EXISTS` |
| Un usuario no puede tener dos veces el mismo rol | `UNIQUE (user_id, role_id)` | `409 ASSIGNMENT_EXISTS` (T06) |
| Una asignación puede **desactivarse** sin borrarse | `status` en `user_roles` | `PATCH /api/v1/user-roles/:id` con `status: inactive`; el permiso deja de aplicar (T07) |
| Una asignación inactiva no concede permisos | consulta de autorización filtra `user_roles.status = 'active'` | `allowed:false` con `reason: assignment_inactive` |
| No existen asignaciones huérfanas | claves foráneas | `404 USER_NOT_FOUND` / `404 ROLE_NOT_FOUND` |
| Borrar un usuario borra sus asignaciones | `ON DELETE CASCADE` | las asignaciones desaparecen |
| Borrar un rol con asignaciones se impide | `ON DELETE RESTRICT` | `409 ROLE_IN_USE` |
| `username` entre 3 y 64 caracteres | `CHECK` | `422 VALIDATION_ERROR` |
| Correo con formato válido | `CHECK` | `422 VALIDATION_ERROR` |
| Estado siempre en el catálogo | `CHECK` `active`/`inactive`/`locked` | `422 VALIDATION_ERROR` |
| Contraseña siempre hasheada | capa de aplicación (Argon2id) + `CHECK` de longitud mínima | nunca hay texto plano |
| Roles solo del catálogo | sembrado + `CHECK` de formato `^[A-Z][A-Z0-9_]{2,31}$` | sin roles inventados |
| `updated_at` automático | trigger | no se puede olvidar actualizarlo |

---

## 4. Catálogo de estados

| Entidad | Valores | Efecto |
|---|---|---|
| `users.status` | `active`, `inactive`, `locked` | Solo `active` recibe decisión `allowed:true`; `inactive`/`locked` → `user_inactive` |
| `roles.status` | `active`, `inactive` | Un rol `inactive` no concede permisos aunque la asignación exista |
| `user_roles.status` | `active`, `inactive` | Una asignación `inactive` no concede permisos sin borrar el histórico |
| `service_clients.status` | `active`, `inactive` | Un cliente inactivo no obtiene token de servicio |

---

## 5. Prohibiciones

- No se guarda ningún rol como arreglo, JSON o string concatenado dentro de `users`.
- No se guardan contraseñas en claro, cifradas de forma reversible, ni hashes en logs.
- No se crea ninguna tabla de identidad (ni copia de `users`) en la base de datos de STEGO.
- STEGO no recibe credenciales de esta base de datos en ningún `.env`.
- No se siembra ningún usuario con contraseña por defecto; si se usa un usuario semilla para la demo,
  su contraseña vive en `.env` local y se cambia antes de la sustentación.

---

## 6. Aceptación (T05, T06)

- [ ] Dos roles asignados al mismo usuario: dos filas en `user_roles`, ambas visibles en `GET /api/v1/users`.
- [ ] Un rol asignado a dos usuarios: dos filas distintas, sin colisión.
- [ ] Repetir la misma asignación devuelve `409 ASSIGNMENT_EXISTS` y **no** crea fila.
- [ ] `SELECT count(*) FROM auth.user_roles WHERE user_id = $1 AND role_id = $2` siempre ≤ 1.
- [ ] El script se aplica dos veces seguidas sin error ni filas duplicadas.
- [ ] Un usuario con `status = 'inactive'` no obtiene `allowed:true` en ninguna acción.
- [ ] Desactivar una asignación (`status='inactive'`) cambia la decisión a `allowed:false` en la
      siguiente petición, con el mismo JWT aún vigente (T07, segunda vía).
- [ ] Borrar la asignación (`DELETE`) produce el mismo efecto observable (T07, primera vía).
