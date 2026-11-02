# Decisiones de alcance

Registro de lo que **se evaluó y se dejó fuera**, con el motivo y el costo de retomarlo. Sirve para
dos cosas: que nadie vuelva a discutirlo, y que el informe pueda justificar el alcance con evidencia en
lugar de con un "no nos dio tiempo".

Estado de cada entrada: **PARKED** (evaluado, fuera de esta entrega) · **REJECTED** (descartado, no
aplica) · **DEFERRED** (se retoma si sobra tiempo).

---

## D-001 · Pipeline CI con análisis de vulnerabilidades en el merge — PARKED

**Requisito original (opcional):** pipeline en el que, en el último punto de entrada al hacer un merge,
un modelo (no LLM) analice vulnerabilidades; un "rack" para analizar el código y refactorizar los
hallazgos, con LLM permitido en la refactorización.

**Decisión:** fuera del alcance de la entrega del 2026-11-04.

### Por qué

| Motivo | Detalle |
|---|---|
| Costo de tiempo | Mínimo ~8 h de implementación + validación, sobre un equipo que todavía no termina el backend obligatorio |
| No está en la rúbrica | Los 6 criterios (20 pts) no lo mencionan; su valor es indirecto, vía criterio 6 |
| Depende de decisiones no tomadas | Necesita el lenguaje y el layout definitivos de ambos servicios |
| Costo operativo | Minutos de Actions en repo privado; además el modelo ML exige métricas propias para ser evidencia válida |
| Riesgo de distracción | Introducir un gate con falsos positivos durante la recta final puede bloquear merges y frenar al equipo |

### Ambigüedad no resuelta

- **"rack"** no corresponde a ninguna herramienta de análisis conocida. Las lecturas posibles son un
  agregador de escáneres (imagen que agrupa varias herramientas) o una mala transcripción de otro
  nombre. Cualquier implementación futura debe partir de una aclaración del docente, no de una suposición.
- **"un modelo (no LLM)"**: se interpretó como modelo de ML entrenado (familia Devign/LineVul/VulBERTa)
  y no como escáner determinista. También es una suposición.

### Diseño que quedó listo si se retoma

Documentado en la conversación de diseño. Resumen:

1. **Etapa 0 (local):** gitleaks + Semgrep sobre el diff, sin bloquear.
2. **Etapa 1 (PR abierto):** detección de servicio afectado por rutas cambiadas.
3. **Etapa 2 (rack):** Semgrep CE + Trivy + Gitleaks → SARIF unificado.
4. **Etapa 3 (modelo ML):** solo sobre el diff, **advisory** (`level: note`), nunca bloqueante en la
   primera versión.
5. **Etapa 4 (LLM):** propone el parche como comentario del PR; `continue-on-error`, jamás required.
6. **Etapa 5 (gate):** único check obligatorio; falla por hallazgos deterministas de severidad alta o
   por `gitleaks` con hallazgos.
7. **Etapa 6 (merge queue):** reejecuta el gate; requiere el evento `merge_group` o el check nunca pasa.
8. **Etapa 7 (post-merge):** escaneo completo + SARIF a Security + artefacto de evidencia.

**Notas técnicas para no repetir errores:**
- CodeQL quedó descartado: en repos privados exige GitHub Advanced Security (de pago).
- Semgrep Managed Scans no corre en merge queues y bloquearía el merge; hay que usar una GitHub Action
  con workflow explícito.
- El evento `merge_group` es obligatorio en el workflow si se usa merge queue.

### Qué haría falta para retomarlo

| Pieza | Estimación |
|---|---|
| Esqueleto del workflow + Semgrep + SARIF + required check | ~2 h |
| Trivy + Gitleaks + reglas propias | ~1 h |
| Modelo ML (inferencia + métricas + conversión a SARIF) | ~4 h |
| Job de refactor con LLM | ~1 h |
| Evidencias (ramas con vulnerabilidades sembradas, capturas, tablas) | ~1 h |

**Criterio de corte:** solo se retoma después de que los 13 issues obligatorios estén cerrados y el
ensayo de la sustentación esté completo.

### Impacto en la entrega

Ninguno. La rúbrica no lo evalúa. Si el docente lo pide como entregable aparte, se retoma con el diseño
de arriba ya validado.

---

## D-002 · Stack: Python 3.12 + FastAPI — RESUELTO

**Decisión:** ambos servicios se implementan con el mismo stack del repositorio de referencia del
curso, [`agcudco/product-service-fast-api`](https://github.com/agcudco/product-service-fast-api):

Python 3.12 · FastAPI · Uvicorn · SQLAlchemy 2 (`Mapped`/`mapped_column`) · psycopg 3 ·
pydantic-settings · httpx · PostgreSQL 16 · Docker Compose.

**Por qué:** el curso ya establece la estructura (`app/{api,clients,core,crud,db,models,schemas,security}`),
los nombres de variables, el patrón de cliente HTTP entre servicios y la guía de endpoints. Seguirla
reduce riesgo de integración y hace la sustentación reconocible para el docente.

**Consecuencia:** el detalle está en [`README.md`](../README.md), sección *Repositorio de referencia*.

---

## D-003 · Desviaciones frente a la referencia — RESUELTO

El repositorio de referencia contradice los contratos congelados en cuatro puntos. Ninguna se cambia en
silencio: cada una necesita aprobación de los dueños de AUTH y STEGO, y sube la versión del contrato 7.

| # | Referencia | Contrato actual | Recomendación | Motivo |
|---|---|---|---|---|
| a | Prefijo `/api/v1` (`API_V1_STR`) | sin prefijo de versión | **Adoptar `/api/v1`** | El enunciado lo acepta si se documenta; ambos servicios del curso lo usan. El endpoint interno queda como `/internal/authorization/check` (textual del enunciado) |
| b | `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` + `example.env.dist` | `AUTH_DATABASE_URL` / `STEGO_DATABASE_URL` + `.env.example` | **Adoptar `DB_*`** y `example.env.dist` | Mismo estilo que el curso; `DATABASE_URL` se arma como propiedad en `Settings` |
| c | Paginación `?page=` + `?limit=` (1–100) | `?page_size=` | **Adoptar `limit`** | Consistencia con la guía de endpoints del curso |
| d | JSON en camelCase en algunas respuestas (`accessToken`, `expiresIn`) | `snake_case` en todo | **Mantener `snake_case`** | El contrato 2 y los JSON Schema ya están normalizados; mezclar estilos rompería la validación. El JWT mantiene los claims estándar de RFC 7519 en camelCase nativo |

**Resuelto el 2026-11-02:** se adoptan **a, b y c**; se mantiene **d** (`snake_case`) para no invalidar
los esquemas de `contracts/`. El contrato 7 pasó a `1.1.0` y el índice a `1.1.0`; los endpoints de los
contratos 2, 3 y 5 se actualizaron con el prefijo `/api/v1`.

---

## D-004 · Modelo ML del requisito opcional — CONTEXTO CON SALVEDADES

Nota informativa, no reabre D-001.

El "modelo (no LLM)" del requisito opcional **ya existe** en la cuenta del docente:
[`agcudco/cve-detector-semma`](https://github.com/agcudco/cve-detector-semma).

### Qué es

| Elemento | Detalle |
|---|---|
| Tipo | Ensemble **no LLM**: CodeBERT (`microsoft/codebert-base`, embeddings de 768 dimensiones) + features de patrón + `IsolationForest`, ponderado 75 % patrones / 25 % semántica |
| Lenguajes | Python y JavaScript |
| Vulnerabilidades | SQLi, XSS, command injection, path traversal, deserialización insegura |
| Entrenamiento | 50 000 muestras de CVEfixes; ~2-3 min en GPU; serializa un `.pkl` de ~15 MB |
| Umbral | 0,57 |
| Interfaces | `VulnerabilityModel.analyze_code(code, language)` y una API Flask (`POST /analyze`, `GET /health`) |
| Componentes | `DataFlowAnalyzer`, `TypeInference`, `FalsePositiveFilter` |

Encaja con el stack elegido: Python está entre los lenguajes soportados.

### Las métricas publicadas no sostienen un gate bloqueante

| Métrica | Valor |
|---|---|
| Accuracy | 84,4 % |
| Precision | 85,4 % |
| Recall | 82,5 % |
| F1 | 83,9 % |
| **Specificity** | **33,3 %** |

Una especificidad de 33,3 % significa que **dos de cada tres muestras seguras se clasifican como
vulnerables**. Con ese valor, un *precisión* de 85,4 % solo es aritméticamente posible si el conjunto de
prueba está muy sesgado hacia casos vulnerables (del orden de 80 % vulnerables / 20 % seguros), lo que
no representa código real, donde la mayoría es seguro.

**Consecuencia:** en un pipeline de merge, el modelo inundaría de falsos positivos al equipo. Solo
serviría como **señal advisory**, nunca como check obligatorio. Por vulnerabilidad, el F1 va de 86 %
(SQLi, deserialización) a 50 % (path traversal).

### Costos de integración reales

- Arrastra `torch` + `transformers` + CodeBERT, con embeddings por línea: pesado y lento en CI sin GPU.
- La API Flask del repo no muestra autenticación; exponerla requeriría añadirla.
- Los modelos se cargan con `pickle`: la herramienta usa **deserialización insegura**, que es
  precisamente una de las cinco vulnerabilidades que detecta. Habría que confiar en el origen del `.pkl`
  o re-serializar.
- Requiere fijar versión del modelo y registrar su hash para que un resultado sea reproducible.

### Conclusión

Si el pipeline se retoma, ya no hay que *entrenar* nada: se reutiliza el modelo. Pero el trabajo se
traslada de "construir el modelo" a "validarlo sobre nuestro código y decidir si su especificidad
justifica usarlo siquiera como advisory". **Sigue PARKED** por decisión de alcance.

---

## D-005 · Hallazgos de `ms-users-nestjs` — RESUELTO

Segunda referencia revisada: [`agcudco/ms-users-nestjs`](https://github.com/agcudco/ms-users-nestjs), el
servicio de identidad del taller. Confirma los contratos 1, 2 y 4 en lo esencial (JWT sin roles, roles
releídos de la BD en cada petición, argon2id, 401≠403).

Detalle completo en [`README.md`](../README.md#ms-users-nestjs).

### Hueco detectado — requiere decisión

| # | Hallazgo | Impacto |
|---|---|---|
| e | El Anexo A y el requisito de revocación hablan de "eliminación **o desactivación** de una asignación". Nuestro `user_roles` solo permite **borrar** la fila: no hay forma de desactivar sin perder el registro histórico | `db/auth/001_init.sql`, contrato 5, T07 y la demostración |

**Propuesta:** añadir `status` (`active`/`inactive`) a `user_roles`, manteniendo `DELETE` como segunda
vía. La decisión de autorización pasaría a exigir `user_roles.status = 'active'` **y** `roles.status =
'active'`, lo que ya hace la referencia del curso. Coste: una columna, un `CHECK` y una condición en la
consulta de autorización.

**Resuelto el 2026-11-02:** se aprueba añadir `status` a `user_roles` y aplicar los cinco ajustes
menores (f–j). Contrato 5 ampliado, nueva acción `user_roles.update` y endpoint
`PATCH /api/v1/user-roles/:id`, nuevo `reason: assignment_inactive`, `AUTH_LOGIN_RATE_LIMIT_PER_MINUTE`
a 5, logout a `204`, login con `identifier` y verificación contra hash ficticio, y validación del
`X-Request-Id` entrante. Todo el conjunto sube los contratos a **1.2.0**.

### Ajustes menores aplicados (f–j)

| # | Tema | Actual | Propuesta | Motivo |
|---|---|---|---|---|
| f | Login | Solo `username` | Campo `identifier` que acepte **username o correo** | Ya lo hace el curso; mejor experiencia y una prueba más en T02 |
| g | Rate limit de login | 10/min | 5 por 60 s | Más estricto, igual que el curso |
| h | `POST /api/v1/auth/logout` | `200` | `204 No Content` | Sin cuerpo que devolver |
| i | Mitigación de *timing attack* | No contemplada | Verificar con un hash ficticio cuando el usuario no existe | Cierra un canal lateral en T02 |
| j | `X-Request-Id` de entrada | Se acepta tal cual | Aceptar solo si cumple `^[A-Za-z0-9._-]{1,64}$`; si no, generar | Evita inyección en logs |

### Descartado de esta referencia

- `HS256`: obligaría a compartir el secreto de firma con STEGO, que el enunciado prohíbe.
- `tokenVersion` como mecanismo único de logout: invalida todas las sesiones del usuario; mantenemos
  `revoked_tokens` por `jti`, que permite cerrar una sesión sin tocar las demás.
- PK compuesta en `user_roles`: el Anexo A exige `id (PK)` + `UNIQUE(user_id, role_id)`.
- Campos de usuario adicionales (cédula, nombres, apellidos, fecha de nacimiento, teléfono): el
  enunciado pide la estructura mínima y esos son datos personales que no necesitamos.

---

## Decisiones abiertas

| ID | Pregunta | Bloquea a |
|---|---|---|
| D-006 | ¿Clave asimétrica RS256 del contrato 1, o se veta por ES256? | 04, 07 |
| D-007 | ¿mTLS, o el token de servicio ya congelado en el contrato 3? | 06, 07 |
