# Backend V1 — AUTH + STEGO

Proyecto Integrador del Primer Parcial · **Desarrollo Software Seguro** · ESPE
**Entrega:** miércoles 4 de noviembre de 2026

Dos microservicios REST independientes que constituyen el backend inicial de una aplicación de salas
de chat seguras:

| Servicio | Responsabilidad |
|---|---|
| **AUTH** | Identidad, roles, relación N:M, JWT y decisiones de autorización RBAC |
| **STEGO** | Validación y análisis esteganográfico de imágenes, solo con autorización vigente de AUTH |

El alcance **no** incluye interfaz web o móvil, salas, mensajería en tiempo real, cifrado extremo a
extremo ni restricción de dispositivos.

---

## Estado

| Elemento | Estado |
|---|---|
| Contratos entre servicios | ✅ Congelados v1.0.0 — [`docs/contratos/`](docs/contratos/00-INDICE-Y-DECISIONES.md) |
| Tablero de trabajo (13 actividades) | ✅ [`TAREAS.md`](TAREAS.md) · issues [#1–#13](../../issues) |
| Decisiones de alcance | ✅ [`docs/DECISIONES.md`](docs/DECISIONES.md) |
| Documentación técnica (entregable aparte) | 📋 Índice y criterios en [`docs/DOCUMENTACION-TECNICA.md`](docs/DOCUMENTACION-TECNICA.md) |
| Stack y convenciones | ✅ Definidos por el repositorio de referencia (abajo) |
| Implementación | ✅ AUTH y STEGO implementados — actividades **01–10 y 12** cerradas |

---

## Stack

Definido a partir del repositorio de referencia del curso:

| Pieza | Versión / elección |
|---|---|
| Lenguaje | Python 3.12 |
| Framework HTTP | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.x (estilo `Mapped` / `mapped_column`) |
| Driver | psycopg 3 (`postgresql+psycopg://`) |
| Configuración | pydantic-settings sobre `.env` |
| Cliente HTTP entre servicios | httpx (`AsyncClient` compartido en el `lifespan`) |
| Base de datos | PostgreSQL 16 |
| Contenedores | Docker + Docker Compose |
| Documentación de API | OpenAPI automático (Swagger en `/docs`, ReDoc en `/redoc`) |

Dependencias completas de referencia: [`requirements.txt`](https://github.com/agcudco/product-service-fast-api/blob/main/requirements.txt).

---

## Repositorios de referencia

Dos microservicios del curso sirven como **plantilla**: no se copia código, se adoptan estructura,
nombres y patrones.

| Repo | Rol para nosotros | Stack |
|---|---|---|
| [`product-service-fast-api`](https://github.com/agcudco/product-service-fast-api) | Plantilla de **STEGO**: estructura, cliente HTTP entre servicios, RBAC por dependencia | Python + FastAPI |
| [`ms-users-nestjs`](https://github.com/agcudco/ms-users-nestjs) | Plantilla de **AUTH**: modelo `users`/`roles`/`user_roles`, JWT, guards, filtros y endurecimiento | TypeScript + NestJS |

### `product-service-fast-api`

**https://github.com/agcudco/product-service-fast-api**

Microservicio de productos y categorías con relación N:M. Define la estructura y el estilo que se
adoptan porque es el mismo stack que usamos.

#### Qué se toma de ahí

| Aspecto | Convención del curso |
|---|---|
| Estructura de carpetas | `app/{api,clients,core,crud,db,models,schemas,security}` + `app/main.py` |
| Routers | `app/api/v1/api.py` agrega `app/api/v1/endpoints/*.py`, todos con `prefix` y `tags` |
| Configuración | `app/core/config.py` con `BaseSettings`, `env_file=".env"`, propiedad `DATABASE_URL` armada desde `DB_*` |
| Sesión de BD | `app/db/session.py` con `create_engine(pool_pre_ping=True)` y `SessionLocal` |
| Dependencia de BD | `app/api/deps.py` → `get_db()` con generador y `finally: db.close()` |
| Inicialización | `init_db()` en el `lifespan` + `seed_database()` idempotente si `ENABLE_SEED=true` |
| Seguridad | `app/security/dependencies.py` con `HTTPBearer(auto_error=False)` y `require_roles(*roles)` |
| Roles | `app/security/roles.py` con tuplas constantes por operación |
| Cliente entre servicios | `app/clients/user_service.py` con `httpx.AsyncClient` en `app.state` |
| Trazabilidad | Cabecera `X-Request-Id` propagada del servicio consumidor al de identidad |
| Respuesta de salud | `GET /health` → `{"status": "ok", "service": "<nombre>"}` |
| Plantilla de entorno | `.env.example` (no `.env.example`) |
| Modelos | UUID v4 como PK, `Mapped[...]`, `CheckConstraint` en `__table_args__` |
| Eliminación lógica | Campo de fecha de eliminación en lugar de `DELETE` físico |
| Paginación | `?page=` (≥1) y `?limit=` (1–100) |
| Prefijo de API | `/api/v1`, configurables con `API_V1_STR` |
| Documentación | `README.md`, `GuiaEndpoints.md` con tabla de endpoints y ejemplos, `TallerJWT.md` con la política RBAC |

### Patrón de autenticación delegada que implementa

```
Servicio  ──►  GET {USER_SERVICE}/api/v1/auth/me   (Authorization: Bearer <jwt>)
           ◄──  { userId, username, email, roles[] }

respuesta 200  → usuario autenticado con sus roles VIGENTES
respuesta 401  → 401 al cliente
respuesta 403  → 403 al cliente
respuesta 429 o 5xx → 503 al cliente   (fallo seguro)
otra respuesta → 502 al cliente
respuesta inválida → 502 al cliente
timeout / error de red → 503 al cliente
```

Los roles se consultan **en cada petición**, no se leen del JWT. Es el principio que nuestro contrato 2
formaliza como `POST /internal/authorization/check`.

#### Documentos del curso incluidos ahí

| Archivo | Para qué sirve |
|---|---|
| `README.md` | Guía de clonar, configurar, levantar y verificar |
| `GuiaEndpoints.md` | Tabla de endpoints con ejemplos de petición y respuesta |
| `TallerJWT.md` | Política RBAC por recurso/operación + integración con el servicio de identidad |
| `docker-compose.product-db.yml` | PostgreSQL 16 con healthcheck, puerto 5433 en host |
| `.env.example` | Plantilla de variables sin secretos reales |

### `ms-users-nestjs`

**https://github.com/agcudco/ms-users-nestjs**

Es el **servicio de identidad** del taller: `users`, `roles`, `user_roles`, login con argon2id, JWT,
guards de rol y cierre de sesión. Aunque está en TypeScript, su **modelo de seguridad es el mismo que
ya congelamos**, así que sirve como validación externa del diseño.

#### Qué confirma de nuestros contratos

| Nuestro contrato | Cómo aparece en la referencia |
|---|---|
| **El JWT no lleva roles** (contrato 1) | El payload es `{sub, username, tokenVersion, typ}` y el código comenta literalmente: *"El JWT solamente identifica al usuario. NO almacena roles"* |
| **Los roles se leen de la BD en cada petición** (contrato 2) | `JwtStrategy.validate()` consulta `users → user_roles → roles` en cada request y filtra `estado` de la asignación **y** del rol |
| **Argon2id** (contrato 1) | `argon2.hash(..., {type: argon2id})` |
| **401 ≠ 403** (contrato 4) | `UnauthorizedException` para token inválido, `ForbiddenException` para rol faltante |
| **TTL de 900 s** (contrato 1) | `JWT_EXPIRES_IN_SECONDS=900` |
| **Prefijo `/api/v1`** (contrato 7) | `setGlobalPrefix('api')` + versionado URI `1` |
| **Paginación `page` + `limit`** (contrato 7) | `/users?page=1&limit=20` |
| **Health público** (contrato 7) | `GET /api/v1/health` |

#### Qué se adopta de ahí

| Práctica | Detalle |
|---|---|
| Mitigación de *timing attack* | Si el usuario no existe, igual se ejecuta `argon2.verify()` contra un hash ficticio |
| Identificador de login | Acepta **username o correo** en un solo campo `identifier` |
| Rate limit de login | 5 intentos por 60 s (más estricto que nuestro 10/min) |
| Logout responde `204 No Content` | |
| Cabeceras de seguridad | `useSecurityHeaders()` |
| CORS restrictivo | Lista explícita desde `CORS_ORIGINS`, métodos permitidos acotados |
| Validación de entrada | `whitelist`, `forbidNonWhitelisted`, `forbidUnknownValues` |
| Validación del entorno al arrancar | Esquema (zod) que falla si falta o es inválida una variable — equivalente en Python: `pydantic-settings` |
| `X-Request-Id` | Se acepta del cliente solo si cumple `^[A-Za-z0-9._-]{1,64}$`; si no, se genera |
| Filtro global de excepciones | Nunca filtra stack traces al cliente; el detalle va al log |
| Endurecimiento de Compose | `security_opt: no-new-privileges:true`, puerto de BD atado a `127.0.0.1`, `start_period` en el healthcheck |
| Hash nunca expuesto | Columna con `select: false` + `@Exclude()` |
| Bloqueo optimista | Columna `version` en las entidades |
| Pruebas | Vitest en dos configuraciones: unitarias y e2e |

#### Dónde la referencia **no** se sigue

| Tema | Referencia | Este proyecto | Motivo |
|---|---|---|---|
| Firma del JWT | `HS256` con `JWT_SECRET` compartido | `RS256` con JWKS | Con HS256, STEGO necesitaría el mismo secreto de firma y el enunciado prohíbe que lo tenga |
| Revocación de sesión | `tokenVersion` en `users` (invalida **todas** las sesiones del usuario) | `revoked_tokens` por `jti` (invalida **una** sesión) | Granularidad por sesión, que es lo que modela el contrato 1 |
| PK de `user_roles` | PK compuesta `(user_id, role_id)` | `id` PK + `UNIQUE(user_id, role_id)` | El Anexo A del enunciado exige explícitamente `id` como PK y la restricción única |
| Tabla `roles` | Columna `rol`, sin descripción | `name` + `description` + `status` | El enunciado exige descripción |
| Ruta de perfil | `/auth/me` | `/auth/profile` | El enunciado nombra `/profile` |
| Formato del JSON | camelCase (`accessToken`, `expiresIn`) | `snake_case` | Los JSON Schema de `contracts/` ya están normalizados |
| Variables de BD | `DB_USERNAME`, `DB_DATABASE` | `DB_USER`, `DB_NAME` | Inconsistencia entre los dos repos del curso; seguimos el de FastAPI, que es nuestro stack |
| Campos del usuario | Cédula, nombres, apellidos, fecha de nacimiento, teléfono | Solo el mínimo del Anexo A | El enunciado pide la estructura mínima; los demás son datos personales innecesarios aquí |

---

## Desviaciones de alcance respecto a los dos repositorios

Resumen de lo que se separa de las referencias por exigencia del enunciado. El detalle está en cada
subsección de arriba.

| Tema | Referencias del curso | Este proyecto | Motivo |
|---|---|---|---|
| Roles | `ADMIN`, `OPERADOR`, `CLIENTE` | `ADMIN`, `ANALYST`, `USER` | El enunciado fija esos tres y la rúbrica los evalúa |
| Autorización | El servicio consulta `/auth/me` y aplica listas de roles en código | `POST /internal/authorization/check` devuelve una **decisión** por acción | El enunciado exige un endpoint interno protegido que decida por acción y recurso |
| Firma del JWT | `HS256` con secreto compartido | `RS256` con JWKS; STEGO solo tiene la clave pública | El enunciado prohíbe que STEGO reciba la clave de firma |
| Validación del JWT | Delega todo al servicio de identidad | STEGO verifica firma con JWKS **y** pide la decisión | El enunciado pide verificación criptográfica en el consumidor |
| PK de `user_roles` | PK compuesta `(user_id, role_id)` | `id` PK + `UNIQUE(user_id, role_id)` | El Anexo A exige `id` como PK y la restricción única |
| Migraciones | `create_all()` / sincronización del ORM | Scripts SQL versionados en `db/` | El enunciado pide migraciones o scripts reproducibles |
| Estados | Eliminación lógica por fecha en `users` y `roles` | `status` explícito | El enunciado exige `status` y su efecto sobre la autorización |
| Base de datos | Una base por servicio en contenedores separados | Una instancia, dos bases y dos usuarios | Menos contenedores; el aislamiento se mantiene por credenciales |

---

## Cómo ejecutar

Requisitos: Docker Engine con Compose v2 y `openssl`.

```bash
git clone <URL-del-repositorio>
cd ProyectoIntegrador

# 1. Configuración local: los tres archivos son secretos y no se versionan
cp .env.example .env
cp auth/.env.example auth/.env
cp stego/.env.example stego/.env

# 2. Claves del JWT de desarrollo (van a .secrets/, ignorado por git)
./scripts/gen-dev-keys.sh

# 3. Comprueba que las contraseñas de base coinciden
./scripts/check-env.sh

# 4. Levanta los tres servicios
docker compose up -d --build
```

| URL | Qué |
|---|---|
| `http://localhost:8080/health` | AUTH |
| `http://localhost:8081/health` | STEGO |
| `docker compose exec db psql -U auth_app -d auth` | base de AUTH (el puerto 5432 no se publica) |

**Primer arranque.** `db/init/00-databases.sh` crea los roles `auth_app` y `stego_app`, las bases
`auth` y `stego`, y aplica las dos migraciones. Cada rol queda como dueño de su base y sin `CONNECT`
sobre la del otro. Esos scripts solo corren sobre un volumen vacío: para repetir el aprovisionamiento,
`docker compose down -v`.

**Operación.** `docker compose down` detiene sin borrar datos; `docker compose up -d auth` levanta un
servicio con su base. Puertos, redes y variables son los del
[contrato 7](docs/contratos/06-puertos-env-rutas.md).

---

## Estructura

```
.
├── auth/                     # AUTH: Dockerfile, .env.example, app/ (esqueleto de la 01)
├── stego/                    # STEGO: Dockerfile, .env.example, app/ (esqueleto de la 01)
├── contracts/                # JSON Schema de los contratos entre servicios
├── db/
│   ├── init/00-databases.sh  # roles, bases y migraciones del primer arranque
│   ├── auth/001_init.sql
│   └── stego/001_init.sql
├── docs/
│   ├── contratos/            # contratos congelados
│   └── DECISIONES.md         # alcance y decisiones
├── evidence/                 # pendiente: salidas de pruebas (actividad 12)
├── samples/                  # pendiente: imágenes de prueba (actividad 12)
├── scripts/                  # gen-dev-keys.sh · check-env.sh
├── .env.example              # secretos de infraestructura para Compose
├── docker-compose.yml
├── TAREAS.md
└── README.md
```

No se versionan: `.env`, `auth/.env`, `stego/.env`, `.secrets/`, `evidence/raw/` ni `samples/generated/`.

---

## Pendiente en este README

- [x] Instrucciones de clonar, configurar y levantar (ID 01 · doc 09)
- [x] Variables de entorno definitivas de cada servicio
- [x] Comandos de inicialización de la base
- [x] Comandos de pruebas
- [x] Colección Postman/Insomnia (ID 10 · doc 10)

---

## Pruebas

```bash
./scripts/gen-samples.py     # muestras reproducibles (solo la primera vez)
./scripts/run-tests.sh       # levanta el stack, aprovisiona el admin y ejecuta la suite
```

La suite corre contra los dos servicios por HTTP real y deja la salida en `evidence/`:
identidad, decisiones de autorización, los once pasos de validación, el detector LSB,
propiedad de resultados y el envoltorio de error. Incluye el caso de fallo seguro:
con AUTH detenido, `analyze` responde `503 AUTHORIZATION_UNAVAILABLE` y no se crea
ninguna fila en `stego.analyses`.

La colección REST está en
[`docs/coleccion-rest.postman_collection.json`](docs/coleccion-rest.postman_collection.json)
y se ejecuta con Postman, Insomnia o `newman`.

| Servicio | OpenAPI |
|---|---|
| AUTH | `http://localhost:8080/openapi.json` · `/docs` |
| STEGO | `http://localhost:8081/openapi.json` · `/docs` |


---

## Documentación relacionada

| Documento | Contenido |
|---|---|
| [`docs/contratos/00-INDICE-Y-DECISIONES.md`](docs/contratos/00-INDICE-Y-DECISIONES.md) | Los siete contratos congelados y sus reglas de cambio |
| [`docs/contratos/01-jwt.md`](docs/contratos/01-jwt.md) | Perfil JWT: claims, firma, validación |
| [`docs/contratos/02-autorizacion-interna.md`](docs/contratos/02-autorizacion-interna.md) | Decisión de autorización y autenticación entre servicios |
| [`docs/contratos/03-matriz-permisos.md`](docs/contratos/03-matriz-permisos.md) | Acciones, roles y endpoints |
| [`docs/contratos/04-esquema-identidad.md`](docs/contratos/04-esquema-identidad.md) | Modelo N:M de identidad |
| [`docs/contratos/05-contrato-analisis.md`](docs/contratos/05-contrato-analisis.md) | Validación de archivos y resultado de análisis |
| [`docs/contratos/06-puertos-env-rutas.md`](docs/contratos/06-puertos-env-rutas.md) | Puertos, variables y convenciones |
| [`TAREAS.md`](TAREAS.md) | Tablero de trabajo del equipo |
| [`docs/DECISIONES.md`](docs/DECISIONES.md) | Alcance y decisiones abiertas |
| [`docs/DOCUMENTACION-TECNICA.md`](docs/DOCUMENTACION-TECNICA.md) | Guía del documento técnico que se entrega aparte |

> Los archivos Markdown de este repositorio son **guías de trabajo**. La documentación técnica que se
> evalúa es un documento separado y su índice obligatorio está en
> [`docs/DOCUMENTACION-TECNICA.md`](docs/DOCUMENTACION-TECNICA.md).
