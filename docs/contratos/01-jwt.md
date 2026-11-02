# Contrato 1 — Perfil JWT

**Estado:** CONGELADO v1.0.0 · **Servicios:** AUTH (emite y valida), STEGO (solo verifica)

---

## 1. Algoritmo y claves

| Elemento | Valor congelado |
|---|---|
| Algoritmo (`alg`) | `RS256` obligatorio |
| Tipo (`typ`) | `JWT` |
| `kid` | Obligatorio en la cabecera, presente en JWKS |
| Tamaño de clave | RSA ≥ 2048 bits |
| Generación | Al aprovisionar; la clave privada **nunca** se versiona y **nunca** sale de AUTH |
| Clave pública | `GET /.well-known/jwks.json` en AUTH (público, sin secretos) |
| Rotación | Nueva entrada en JWKS con `kid` nuevo; el anterior sigue publicado hasta que expiren los tokens emitidos |

STEGO recibe **únicamente** material público. STEGO no firma, no emite tokens y no conoce la clave
privada de firma.

`alg` se valida contra una lista cerrada (`RS256`). Se rechazan `none`, `HS256` y cualquier variante no
listada — es la defensa contra *algorithm confusion*.

---

## 2. Claims (access token)

```json
{
  "iss": "auth-service",
  "sub": "3f1c2a9e-5b7d-4c8e-9a10-7d6f5e4b3c21",
  "aud": ["auth-api", "stego-api"],
  "iat": 1762100000,
  "exp": 1762100900,
  "jti": "b0e1d2c3-4a5f-4e6d-8c9b-0a1b2c3d4e5f",
  "token_use": "access",
  "username": "ana.perez"
}
```

| Claim | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `iss` | string | sí | Exactamente `auth-service` |
| `sub` | string (UUID v4) | sí | `users.id`; es la **única** identidad reconocida |
| `aud` | array de string | sí | Contiene `auth-api` y `stego-api`; cada servicio exige la suya |
| `iat` | number (epoch s) | sí | Hora de emisión |
| `exp` | number (epoch s) | sí | `iat + AUTH_ACCESS_TOKEN_TTL_SECONDS` (900 s) |
| `jti` | string (UUID v4) | sí | Necesario para revocación por `logout` |
| `token_use` | string | sí | `access` para tokens de usuario, `service` para tokens de servicio |
| `username` | string | no | Datos de presentación; **nunca** se usa para decidir |

### Prohibido dentro del token

- Roles, permisos, scopes de negocio o cualquier dato de autorización. La autorización **siempre** se
  resuelve contra la base de datos vigente.
- `password_hash`, correo, documento de identidad o cualquier dato personal adicional.
- Claves, secretos o `kid` privado.

---

## 3. Validación obligatoria

STEGO y AUTH aplican el mismo orden. El primer fallo corta la cadena.

| # | Verificación | Fallo → |
|---|---|---|
| 1 | Cabecera decodificable, `alg` = `RS256`, `typ` = `JWT`, `kid` conocido | `401 TOKEN_INVALID` |
| 2 | Firma válida con la clave pública del `kid` | `401 TOKEN_INVALID` |
| 3 | `iss` = `auth-service` | `401 TOKEN_INVALID` |
| 4 | `aud` contiene el identificador del servicio que valida | `401 TOKEN_INVALID` |
| 5 | `token_use` = `access` | `401 TOKEN_INVALID` |
| 6 | `exp` > ahora (desfase de reloj permitido: 60 s), `iat` no futuro (±60 s) | `401 TOKEN_EXPIRED` |
| 7 | `jti` no está en `auth.revoked_tokens` | `401 TOKEN_REVOKED` |
| 8 | `sub` es UUID y el usuario existe con `status = 'active'` | `401 TOKEN_INVALID` (usuario inexistente) / `401 SUBJECT_INACTIVE` (desactivado) |

Ninguno de estos pasos consulta roles. La autorización es el paso siguiente (contrato 2).

### Regla del login

El login valida contra `users` vigentes y **siempre ejecuta la verificación de contraseña**, incluso
cuando el usuario no existe, comparando contra un hash ficticio precalculado. Así el tiempo de respuesta
no revela si un nombre de usuario o correo existe. El campo de entrada se llama `identifier` y acepta
tanto `username` como `email`.

---

## 4. Ciclo de vida

| Evento | Efecto |
|---|---|
| `POST /api/v1/auth/login` (credenciales válidas) | Emite access token con TTL 900 s |
| `POST /api/v1/auth/logout` | Responde `204` e inserta el `jti` en `auth.revoked_tokens` con su `exp`; ese token deja de servir de inmediato |
| Expiración natural | `exp` superado |
| Cambio de rol o de estado del usuario | **No** invalida el token: el token sigue siendo válido pero la decisión de autorización cambia |
| Desactivación del usuario | El token deja de servir porque el paso 8 de validación falla |

La limpieza de `revoked_tokens` se hace por trabajo periódico o borrado de lo expirado; no puede
bloquear el login.

---

## 5. Gestión de claves

- La clave privada se inyecta en AUTH por secreto montado y se referencia con
  `AUTH_JWT_PRIVATE_KEY_PATH`. **No** se copia al repositorio ni a la imagen Docker en texto plano.
- `example.env.dist` solo contiene la **ruta** a la clave, con un marcador de posición.
- La clave pública se expone por JWKS en AUTH y STEGO la obtiene por HTTP en
  `STEGO_AUTH_JWKS_URL` (caché corta, con reintento y sin bloquear la operación si falla: **falla
  cerrado**).
- Rotación: publicar el nuevo `kid` en JWKS → empezar a firmar con él → retirar el `kid` anterior
  cuando expiren los tokens emitidos con él. El procedimiento se documenta en el informe aunque en la
  entrega se use una sola clave.

---

## 6. Aceptación

- [ ] Un token manipulado (payload cambiado) devuelve `401 TOKEN_INVALID`.
- [ ] Un token firmado con otra clave devuelve `401 TOKEN_INVALID`.
- [ ] Un token `alg: none` devuelve `401 TOKEN_INVALID`.
- [ ] Un token vencido devuelve `401 TOKEN_EXPIRED`.
- [ ] Un token tras `logout` devuelve `401 TOKEN_REVOKED`.
- [ ] Un token de usuario con `role` añadido a mano en el payload **no otorga acceso**.
- [ ] JWKS responde con la clave pública y sin ningún dato privado.
