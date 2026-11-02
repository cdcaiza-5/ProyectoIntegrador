# Contratos congelados — Backend V1 (AUTH + STEGO)

**Versión:** 1.4.0
**Estado:** CONGELADO
**Fecha de congelamiento:** 2026-11-02
**Entrega del proyecto:** 2026-11-04
**Alcance:** define los siete acuerdos que ambos servicios y el equipo de documentación deben
respetar antes de escribir código. No contiene implementación.

---

## 1. Qué queda congelado

| # | Acuerdo | Documento | Dueño de la implementación |
|---|---|---|---|
| 1 | Perfil JWT (claims, algoritmo, claves, validación) | [01-jwt.md](01-jwt.md) | AUTH (emisión) / STEGO (verificación) |
| 2 | Contrato `POST /internal/authorization/check` | [02-autorizacion-interna.md](02-autorizacion-interna.md) | AUTH (servidor) / STEGO (cliente) |
| 3 | Autenticación servicio→servicio | [02-autorizacion-interna.md](02-autorizacion-interna.md) | Integración (un solo responsable) |
| 4 | Matriz acción × rol × endpoint | [03-matriz-permisos.md](03-matriz-permisos.md) | AUTH (decisión) / STEGO (recurso) |
| 5 | Esquema de base de datos de identidad | [04-esquema-identidad.md](04-esquema-identidad.md) + [`db/auth/001_init.sql`](../../db/auth/001_init.sql) | AUTH |
| 6 | Contrato de análisis y resultado | [05-contrato-analisis.md](05-contrato-analisis.md) | STEGO |
| 7 | Puertos, variables de entorno y rutas | [06-puertos-env-rutas.md](06-puertos-env-rutas.md) | DevOps |

Esquemas legibles por máquina (validación automática en CI y en pruebas):

- [`contracts/authz-check.request.schema.json`](../../contracts/authz-check.request.schema.json)
- [`contracts/authz-check.response.schema.json`](../../contracts/authz-check.response.schema.json)
- [`contracts/analysis-result.schema.json`](../../contracts/analysis-result.schema.json)

---

## 2. Decisiones tomadas por defecto (vetables hasta el primer commit de código)

Si el equipo prefiere otra opción, se cambia **en este documento** antes de que exista código, y se
sube la versión. Después de la primera implementación mergeada, un cambio cuesta re-trabajo en dos
servicios más documentación.

| Decisión | Valor congelado | Motivo | Alternativa si hay veto |
|---|---|---|---|
| Algoritmo de firma | `RS256` (RSA 2048, clave asimétrica) | Clave privada solo en AUTH; STEGO verifica con la clave pública. RFC 8725 recomienda algoritmos asimétricos. Es el que mejor soportan todas las librerías JWT. | `ES256` (más corto, mismo principio) |
| Distribución de clave | JWKS público en AUTH: `GET /.well-known/jwks.json` | Rotación por `kid` sin redespliegue de STEGO. | Clave pública en archivo montado |
| Vigencia del access token | `900` s (15 min) | Suficiente para demostrar T07 (retirar rol y reutilizar el JWT vigente) sin esperas. | `600` s |
| Autenticación servicio→servicio | `client_credentials` sobre red interna de Docker → **token de servicio** de 300 s | Verificable, sin emitir certificados en 48 h; la red interna cubre el "canal seguro". | mTLS (mejor, más trabajo: CA, certs, montajes) |
| Base de datos | Una instancia PostgreSQL 16 con **dos bases separadas** (`auth`, `stego`) y usuarios distintos | Cumple "persistencia exclusiva de AUTH" sin levantar dos motores. | Dos contenedores de BD |
| Asignación duplicada | `409 ASSIGNMENT_EXISTS` (no éxito silencioso) | Demuestra la restricción `UNIQUE` de forma observable en T06. | `200` idempotente |
| `roles` dentro del JWT | **Prohibido** | Si el token no lleva autorización, es imposible autorizar con datos viejos. Refuerza el criterio 4. | Permitido solo como dato informativo, nunca evaluado |
| Umbral de anomalía LSB | Variable `STEGO_LSB_ANOMALY_THRESHOLD`, valor inicial `0.75` | El valor final **debe** calibrarse con las muestras y justificarse en el informe. | Cambiar el método por completo |
| Almacenamiento de archivos | Volumen Docker `stego_storage`, sin exposición pública | Aísla la carga y permite controlar retención. | Ruta del host |
| Zona horaria / formato | UTC, ISO-8601 `Z`, UUID v4 | Evita ambigüedad en auditoría y comparaciones de tiempo. | — |

---

## 3. Reglas de cambio

1. Toda modificación a un contrato se propone en un commit etiquetado `contrato(alcance): ...`,
   sube la versión y se anota en la tabla de abajo.
2. Cambiar un contrato exige **dos aprobaciones**: dueño de AUTH y dueño de STEGO. Un cambio de
   contrato nunca se aprueba "de paso" dentro de una feature.
3. Cambios de versión `MAJOR` (campos obligatorios, rutas, códigos) requieren avisar a quien ya esté
   implementando en ese momento.
4. Después de la entrega (`2026-11-04`) este documento queda como evidencia del diseño; no se edita
   para "hacer que coincida" con la implementación. Si difieren, se documenta la desviación.

### Registro de versiones

| Versión | Fecha | Cambio | Aprobó AUTH | Aprobó STEGO |
|---|---|---|---|---|
| 1.0.0 | 2026-11-02 | Congelamiento inicial | | |
| 1.1.0 | 2026-11-02 | Adopción de las convenciones del repositorio de referencia del curso (contrato 7): `/api/v1`, `DB_*`, `.env.example`, paginación con `limit` | | |
| 1.4.0 | 2026-11-02 | Procedimiento de bootstrap del primer administrador (contrato 5): CLI idempotente, sin red, sin secreto en reposo y auditado | | |
| 1.3.0 | 2026-11-02 | La plantilla de entorno vuelve a `.env.example`, nombre exigido por el enunciado (§3) | | |
| 1.2.0 | 2026-11-02 | `status` en `user_roles` para desactivar asignaciones sin borrarlas (contrato 5); acción `user_roles.update` y endpoint `PATCH /api/v1/user-roles/:id` (contrato 4); `reason: assignment_inactive` (contrato 2); login con `identifier` y verificación contra hash ficticio (contrato 1); logout `204`, rate limit 5/60 s y validación de `X-Request-Id` (contratos 4 y 7) | | |

---

## 4. Lo que NO está congelado (cada quien decide)

- Lenguaje y framework de cada servicio (deben justificarse en el informe).
- ORM/migrador, librería de tests, librería de logs, formato de fechas internas.
- Estructura de carpetas interna, nombres de clases, estilo de código.
- **Nada de lo anterior puede alterar** rutas, JSONs, códigos HTTP, nombres de variables de entorno,
  puertos ni esquema de base de datos definidos aquí.

---

## 5. Verificación del congelamiento (esto debe pasar antes de la demostración)

- [ ] Los tres JSON Schema validan los ejemplos reales generados por ambos servicios.
- [ ] Una instancia limpia levanta con `docker compose up` usando solo los nombres de `06-puertos-env-rutas.md`.
- [ ] AUTH responde `/.well-known/jwks.json` y STEGO rechaza un token firmado con otra clave.
- [ ] `POST /internal/authorization/check` devuelve exactamente los campos del contrato (sin extras).
- [ ] La matriz de `03-matriz-permisos.md` coincide con lo implementado en los dos servicios.
- [ ] `db/auth/001_init.sql` y `db/stego/001_init.sql` se aplican sin errores en una base vacía.
- [ ] Un análisis real produce un JSON que valida contra `analysis-result.schema.json`.
- [ ] Ningún servicio escribe en el esquema del otro.

---

## 6. Cómo arrancar con esto (orden de lectura por rol)

| Rol | Lee en este orden | Primera acción concreta |
|---|---|---|
| Dueño de AUTH | 01 → 04 → 03 → 02 | Aplicar `db/auth/001_init.sql` y montar login + JWT |
| Dueño de STEGO | 01 → 05 → 03 → 02 | Esqueleto del servicio + validación de archivos (no necesita a AUTH para empezar) |
| Integración | 02 → 01 → 06 | Token de servicio + `authorization/check` + fallo seguro |
| DevOps | 06 → 04 → 05 | `docker-compose.yml`, redes, volúmenes, `.env.example` |
| Documentación / pruebas | 03 → 05 → 02 → 06 | Matriz de riesgos, diagramas y colección Postman con los casos T01–T12 |

Regla de oro para el equipo: si algo no está en estos documentos, **no se inventa en el código**; se
propone aquí, se aprueba y se versiona. Si algo de aquí no se puede cumplir, se documenta la desviación
en el informe en lugar de cambiar el contrato en silencio.
