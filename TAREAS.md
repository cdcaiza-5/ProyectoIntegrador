# TAREAS — Backend V1 (AUTH + STEGO)

Tablero de actividades del equipo. Cada fila es una unidad de trabajo con **un solo dueño**.

- Los **contratos** (`docs/contratos/`) dicen *cómo debe verse y comportarse*.
- Este documento dice *quién lo construye, en qué orden y cuándo está terminado*.

**Regla:** si algo no está en los contratos, no se inventa en el código. Se propone en
[`00-INDICE-Y-DECISIONES.md`](docs/contratos/00-INDICE-Y-DECISIONES.md), se aprueba y se versiona.

---

## Dos numeraciones

El tablero usa **dos números** y conviene no confundirlos:

| | Qué significa | Para qué sirve |
|---|---|---|
| **ID** (`01`–`13`) | Orden del **documento**: sigue la estructura del enunciado (§2.2 AUTH → §2.3 STEGO → §2.4 integración → §3 entregables → §5.4 pruebas → sustentación) | Referencia estable. Es el número que se cita en contratos, commits y documentación |
| **Orden** (1–13) | Orden real de **ejecución**, calculado a partir de las dependencias | Es la secuencia en la que se trabaja |

Los issues de GitHub se crearon en orden de ejecución, así que **el número del issue coincide con la
columna `Orden`**, no con el `ID`.

```
Orden 1  → ID 09   (DevOps)
Orden 2  → ID 01   (AUTH datos)
Orden 3  → ID 05   (STEGO intake)
...
```

---

## 1. Tablero (ordenado por ejecución)

| ID | Orden | Fase | Actividad | Dueño | Contratos | Depende de | Rúbrica |
|---|---|---|---|---|---|---|---|
| **09** | 1 | A | DevOps: Compose, redes, volúmenes, entorno | DevOps | 7 | — | 1 (3,0) |
| **01** | 2 | B | AUTH — capa de datos de identidad | AUTH | 5 | — | 2 (3,0) |
| **05** | 3 | B | STEGO — esqueleto, intake y validación de archivos | STEGO | 6, 7 | — | 5 (5,0) |
| **02** | 4 | C | AUTH — login, JWT y claves | AUTH | 1, 5 | 01 | 3 (3,0) |
| **03** | 5 | C | AUTH — CRUD administrativo | AUTH | 4, 5 | 01, 02 | 2 (3,0) |
| **04** | 6 | D | AUTH — motor RBAC y endpoint interno | AUTH | 2, 3, 4 | 02, 03 | 4 (4,0) |
| **07** | 7 | D | Integración STEGO → AUTH (token de servicio, fallo seguro) | Integración | 1, 2, 3 | 02, 04, 05 | 4 (4,0) |
| **06** | 8 | E | STEGO — detección LSB, resultados y persistencia | STEGO | 6 | 05 | 5 (5,0) |
| **08** | 9 | E | Seguridad transversal: errores, logs, límites | Integración | 6, 7 | 02, 05 | 6 (2,0) |
| **10** | 10 | F | OpenAPI de ambos servicios + colección REST | Docs | 3, 6, 7 | 04, 06 | 6 (2,0) |
| **11** | 11 | G | Informe técnico, diagramas y matriz de riesgos | Docs | 3, 5, 6 | — | 6 (2,0) |
| **12** | 12 | F | Pruebas T01–T12, muestras y evidencias | Pruebas | 3, 6, 7 | 07, 08 | 6 (2,0) |
| **13** | 13 | F | Ensayo y guion de la sustentación | Demo | todos | 12 | 6 (2,0) |

### Fases

| Fase | Orden | Actividades | Se puede empezar |
|---|---|---|---|
| **A** | 1 | 09 | Ya |
| **B** | 2–3 | 01, 05 | En paralelo con A |
| **C** | 4–5 | 02, 03 | Cuando 01 cierre |
| **D** | 6–7 | 04, 07 | Cuando 02 y 03 cierren |
| **E** | 8–9 | 06, 08 | 06 desde que 05 cierre; 08 desde 02 |
| **F** | 10, 12–13 | 10, 12, 13 | Cuando 07 y 08 cierren |
| **G** | 11 | 11 | **Ya, en paralelo con todo** (no depende de código) |

### Camino crítico

```
09 → 01 → 02 → 04 → 07 → 12 → 13
```

Si algo se retrasa, se recorta primero lo que **no** está en esta cadena: 10 y 11 se pueden cerrar con
lo que exista, y 08 se limita a lo demostrable.

### Asignación de nombres (completar antes de empezar)

| ID | Orden | Asignado a |
|---|---|---|
| 09 | 1 | |
| 01 | 2 | |
| 05 | 3 | |
| 02 | 4 | |
| 03 | 5 | |
| 04 | 6 | |
| 07 | 7 | |
| 06 | 8 | |
| 08 | 9 | |
| 10 | 10 | |
| 11 | 11 | |
| 12 | 12 | |
| 13 | 13 | |

---

## 2. Detalle y criterio de terminado (por ID)

Cada título indica su orden de ejecución entre paréntesis.

### 01 — AUTH: capa de datos de identidad _(orden 2)_
**Entregable:** proyecto AUTH con su `Dockerfile`, `example.env.dist` y migración aplicada.
**Hecho cuando:**
- [ ] `db/auth/001_init.sql` corre sin errores en base vacía y es idempotente.
- [ ] `users`, `roles`, `user_roles` con FK y `UNIQUE(user_id, role_id)`.
- [ ] `user_roles.status` permite desactivar una asignación sin borrarla.
- [ ] Roles `ADMIN`, `ANALYST`, `USER` sembrados.
- [ ] Repositorios de usuarios, roles y asignaciones (sin arreglos en memoria ni constantes).
- [ ] Asignación duplicada devuelve `409 ASSIGNMENT_EXISTS` y no crea fila (T06).

### 02 — AUTH: login, JWT y claves _(orden 4)_
**Entregable:** `POST /api/v1/auth/login`, `/api/v1/auth/profile`, `/api/v1/auth/logout` y JWKS.
**Hecho cuando:**
- [ ] Contraseñas con Argon2id; nunca texto plano.
- [ ] Login acepta `identifier` (username o correo) y siempre ejecuta la verificación de contraseña, incluso si el usuario no existe.
- [ ] Par RSA generado; privada solo en AUTH, pública en `/.well-known/jwks.json`.
- [ ] Token con `iss`, `sub`, `aud`, `iat`, `exp`, `jti`, `token_use`; **sin roles**.
- [ ] Validación en el orden de 8 pasos del contrato 1.
- [ ] `logout` responde `204` e inserta el `jti` en `revoked_tokens`.
- [ ] Credenciales inválidas → `401 AUTH_INVALID_CREDENTIALS`; más de 5 intentos en 60 s → `429`.

### 03 — AUTH: CRUD administrativo _(orden 5)_
**Entregable:** `/api/v1/users`, `/api/v1/roles` y `/api/v1/user-roles` completos, solo ADMIN.
**Hecho cuando:**
- [ ] `POST/GET /api/v1/users` y `PATCH /api/v1/users/:id` (incluye activar/desactivar).
- [ ] `POST/GET /api/v1/roles` y `PATCH /api/v1/roles/:id`.
- [ ] `POST /api/v1/user-roles`, `PATCH /api/v1/user-roles/:id` (activar/desactivar) y `DELETE /api/v1/user-roles/:id`.
- [ ] Todo protegido por decisión RBAC contra la BD, no por claim del JWT.
- [ ] Un `ANALYST` recibe `403` en todos estos endpoints.

### 04 — AUTH: motor RBAC y endpoint interno _(orden 6)_
**Entregable:** `POST /internal/authorization/check` y `POST /internal/service-token`.
**Hecho cuando:**
- [ ] Respuesta con exactamente los 9 campos del contrato 2.
- [ ] Relee usuario, asignación y rol en **cada** petición; exige los tres `status` activos.
- [ ] Catálogo de `reason` completo; acción desconocida → `allowed:false` + `unknown_action`.
- [ ] Token de servicio obligatorio; token de usuario en `/internal/*` → `401 SERVICE_AUTH_FAILED`.
- [ ] Retirar **o desactivar** una asignación cambia la decisión en la siguiente petición (T07).

### 05 — STEGO: esqueleto, intake y validación _(orden 3)_
**Entregable:** proyecto STEGO con `POST /api/v1/steganography/analyze` validando de verdad.
**Hecho cuando:**
- [ ] `db/stego/001_init.sql` aplicado.
- [ ] Tubería de validación de 11 pasos del contrato 6, en orden.
- [ ] `413` por tamaño, `415` por tipo/firma, `422` por archivo corrupto (T10).
- [ ] Archivos guardados en cuarentena con nombre aleatorio, sin exposición pública.
- [ ] Nada se persiste si la validación falla.

### 06 — STEGO: detección LSB y resultados _(orden 8)_
**Entregable:** analizador real + `GET /api/v1/steganography/results/:id`.
**Hecho cuando:**
- [ ] Análisis LSB estadístico implementado con umbral configurable.
- [ ] Clasificación `sin_indicios` / `sospechosos` / `no_concluyentes` / `error` + `action` según tabla.
- [ ] Registro con `sha256`, técnica, indicadores, política y `limitations` no vacío.
- [ ] JSON valida contra `contracts/analysis-result.schema.json`.
- [ ] Imagen limpia y su versión con carga LSB dan resultados distintos y reales (T09).
- [ ] Lectura de resultado ajeno → `403 RESULT_FORBIDDEN`; inexistente → `404` (T11).

### 07 — Integración STEGO → AUTH _(orden 7)_
**Entregable:** flujo bearer completo con decisión vigente y fallo seguro.
**Hecho cuando:**
- [ ] STEGO verifica el JWT con JWKS y luego pide la decisión a AUTH.
- [ ] Token de servicio obtenido y renovado a los 240 s.
- [ ] AUTH caído / timeout / respuesta inválida → `503 AUTHORIZATION_UNAVAILABLE` sin procesar (T08).
- [ ] STEGO ignora cabeceras y campos de permisos enviados por el cliente.
- [ ] STEGO no tiene credenciales de la base de AUTH.

### 08 — Seguridad transversal _(orden 9)_
**Entregable:** manejo de errores, logging y límites homogéneos en ambos servicios.
**Hecho cuando:**
- [ ] Envoltorio de error único con `code`, `message`, `request_id`, `timestamp`.
- [ ] Logs de auditoría sin contraseñas, claves ni JWT completos (T12).
- [ ] Rate limiting en login y en analyze.
- [ ] Validación de entrada en todos los DTO; sin stack traces en respuestas.
- [ ] `X-Request-Id` validado y propagado de STEGO a AUTH.

### 09 — DevOps: Compose, redes, volúmenes y entorno _(orden 1)_
**Entregable:** `docker-compose.yml` reproducible + plantillas de entorno + README de ejecución.
**Hecho cuando:**
- [ ] `docker compose up` levanta `auth`, `stego` y `db` sin pasos manuales.
- [ ] Cada servicio arranca y se detiene por separado (T01).
- [ ] `backend_net` interno, `edge_net` para los puertos publicados, `db` sin publicar.
- [ ] Bases `auth` y `stego` con usuarios distintos y sin permisos cruzados.
- [ ] `auth/example.env.dist` y `stego/example.env.dist` con todas las variables obligatorias y sin secretos.
- [ ] `GET /health` responde en ambos servicios.
- [ ] `README.md` con clonar → configurar → levantar.

### 10 — OpenAPI y colección REST _(orden 10)_
**Entregable:** especificación de ambos servicios + colección Postman/Insomnia.
**Hecho cuando:**
- [ ] OpenAPI de AUTH con todos los endpoints, incluido el interno marcado como solo-servicio.
- [ ] OpenAPI de STEGO con analyze (multipart) y results.
- [ ] Colección con caminos felices y todos los casos de denegación.
- [ ] La colección se ejecuta de punta a punta contra el Compose levantado.

### 11 — Informe técnico y matriz de riesgos _(orden 11)_
**Entregable:** documento con diagramas, justificaciones y matriz.
**Hecho cuando:**
- [ ] Diagrama de arquitectura con límites de confianza y flujo AUTH↔STEGO.
- [ ] Diagrama entidad–relación `users`—`user_roles`—`roles`.
- [ ] Explicación de JWT, RBAC y verificación de roles vigentes.
- [ ] Justificación del método LSB, parámetros, formatos y limitaciones.
- [ ] Justificación de la selección tecnológica: el enunciado no impone lenguaje ni framework, pero exige que la elección se justifique (§2.1).
- [ ] Matriz activo/amenaza/vulnerabilidad/riesgo/control ligada a Zero Trust, Secure by Design, Shift Left e ISO/IEC 27001 y 27034 (sin alegar certificación).

### 12 — Pruebas y evidencias _(orden 12)_
**Entregable:** suite ejecutable + evidencias reproducibles de T01–T12.
**Hecho cuando:**
- [ ] Unitarias: hashing, emisión/validación de token, decisión RBAC, analizador LSB.
- [ ] Funcionales de cada endpoint, incluidos `401/403/413/415`.
- [ ] Seguridad: token manipulado, vencido, `alg:none`, revocación con JWT vivo, AUTH caído, archivo polyglot.
- [ ] Integración: usuario con 2 roles, rol en 2 usuarios, login → analyze → results.
- [ ] Muestras `sample-clean.png`, `sample-lsb.png`, `sample-clean.bmp`, `sample-corrupt.png`, `sample-fake.png`, `sample-huge.png` con script generador versionado.
- [ ] Evidencias en `evidence/` (salidas y logs depurados, sin secretos).

### 13 — Ensayo y guion de la sustentación _(orden 13)_
**Entregable:** guion cronometrado y ensayo completo.
**Hecho cuando:**
- [ ] Guion en el orden exacto: 2 roles a un usuario → rol en 2 usuarios → login → analyze con JWT → denegaciones → retirar rol y reutilizar JWT → AUTH caído → imagen limpia vs. con carga LSB.
- [ ] Cada paso tiene responsable y terminal asignados.
- [ ] Ensayo completo sin errores, con plan B grabado.
- [ ] Repo congelado y etiquetado antes de la entrega.

---

## 3. Calendario (entrega: miércoles 4 de noviembre de 2026)

| Momento | Debe estar listo |
|---|---|
| **Lun 2, tarde** | 09 (Compose) · 01 (DDL) · 05 (esqueleto STEGO) · 11 (diagramas empezados) |
| **Lun 2, noche** | 02 (login + JWT + JWKS) · 06 (analizador LSB con las primeras muestras) |
| **Mar 3, mañana** | 03 (CRUD) · 04 (endpoint interno) · 07 (integración cableada) |
| **Mar 3, tarde** | 08 (seguridad y logs) · 10 (OpenAPI + colección) · 12 (pruebas T01–T12) |
| **Mar 3, noche** | 11 (informe completo) · evidencias · primer ensayo (13) |
| **Mié 4, mañana** | Ensayo final · repo congelado · entrega |

---

## 4. Cobertura de la rúbrica

| Criterio | Puntos | Actividades (ID) |
|---|---|---|
| 1. Arquitectura y Compose | 3,0 | 09, 01, 05 |
| 2. Modelo de identidad | 3,0 | 01, 03 |
| 3. Autenticación JWT | 3,0 | 02 |
| 4. RBAC e integración | 4,0 | 04, 07 |
| 5. Detección de esteganografía | 5,0 | 05, 06 |
| 6. Pruebas y documentación | 2,0 | 08, 10, 11, 12, 13 |

## 5. Cobertura de los escenarios mínimos

| Escenario | Actividad que lo demuestra |
|---|---|
| T01 arranque independiente | 09 |
| T02 login válido/inválido | 02 |
| T03 sin token / manipulado / vencido | 02, 07 |
| T04 USER intenta analizar | 04, 07 |
| T05 N:M persistida | 01, 03 |
| T06 asignación duplicada | 01 |
| T07 rol retirado con JWT vivo | 04, 07 |
| T08 AUTH inaccesible | 07 |
| T09 original vs. carga LSB | 06 |
| T10 archivo inválido/corrupto/grande | 05 |
| T11 análisis ajeno | 06 |
| T12 bitácoras sin secretos | 08 |
