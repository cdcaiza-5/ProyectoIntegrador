# Contrato 6 — Análisis de esteganografía y formato de resultado

**Estado:** CONGELADO v1.0.0 · **Servicio:** STEGO

---

## 1. Endpoints

### `POST /api/v1/steganography/analyze`

| Requisito | Valor |
|---|---|
| Autenticación | `Authorization: Bearer <access token>` |
| Autorización | `steganography.analyze` (ADMIN o ANALYST) + decisión vigente de AUTH |
| `Content-Type` | `multipart/form-data` |
| Campo `file` | obligatorio, único archivo por petición |
| Campo `note` | opcional, texto ≤ 500 caracteres, se guarda solo como metadato |
| Tamaño máximo | `STEGO_MAX_UPLOAD_BYTES` (5 MiB por defecto) |
| Formatos | `image/png`, `image/bmp` (se acepta `image/x-ms-bmp`) |
| Éxito | `201 Created` con el `analysis-result` completo |

### `GET /api/v1/steganography/results/:id`

| Requisito | Valor |
|---|---|
| Autenticación | `Authorization: Bearer <access token>` |
| Autorización | `steganography.results.read` + propiedad (ADMIN ve todo; el resto solo `user_id == sub`) |
| Éxito | `200` con el `analysis-result` |
| Inexistente | `404 RESULT_NOT_FOUND` |
| Ajeno sin ADMIN | `403 RESULT_FORBIDDEN` |

---

## 2. Tubería de validación (en este orden, cortando en el primer fallo)

| # | Paso | Fallo |
|---|---|---|
| 1 | JWT válido (contrato 1) | `401 TOKEN_INVALID` / `TOKEN_EXPIRED` / `TOKEN_REVOKED` |
| 2 | Decisión `steganography.analyze` vigente (contrato 2) | `401` o `403` o `503`, **sin leer el archivo** |
| 3 | `Content-Type` de la petición es `multipart/form-data` | `415 UNSUPPORTED_MEDIA_TYPE` |
| 4 | Existe el campo `file`, uno solo | `422 VALIDATION_ERROR` |
| 5 | Tamaño ≤ `STEGO_MAX_UPLOAD_BYTES` | `413 PAYLOAD_TOO_LARGE` |
| 6 | Extensión en la lista permitida (`.png`, `.bmp`) | `415 UNSUPPORTED_MEDIA_TYPE` |
| 7 | Tipo declarado en la lista permitida | `415 UNSUPPORTED_MEDIA_TYPE` |
| 8 | **Firma real por magic bytes** coherente con el tipo declarado (`89 50 4E 47 0D 0A 1A 0A` para PNG, `42 4D` para BMP) | `415 FILE_SIGNATURE_MISMATCH` |
| 9 | El archivo decodifica como imagen válida del tipo declarado (no truncado, no polyglot, no cero píxeles) | `422 IMAGE_UNPROCESSABLE` |
| 10 | Límites de procesamiento: ancho ≤ 10000 px, alto ≤ 10000 px, píxeles ≤ 25 000 000 | `413 PAYLOAD_TOO_LARGE` |
| 11 | Decisión `allowed:false` en cualquier momento previo | `401` / `403` según §5 del contrato 2 |

El archivo nunca se ejecuta ni se sirve públicamente. Se guarda en
`STEGO_STORAGE_QUARANTINE_PATH` con nombre aleatorio (UUID), extensión canónica y permisos `0640`.
Cuando la validación falla, no se persiste ni el archivo ni un registro en `stego.analyses`.

---

## 3. Formato del resultado (`analysis-result`)

Esquema: `contracts/analysis-result.schema.json`.

```json
{
  "analysis_id": "c1a2b3c4-d5e6-4f70-8a91-b2c3d4e5f607",
  "user_id": "3f1c2a9e-5b7d-4c8e-9a10-7d6f5e4b3c21",
  "filename": "muestra.png",
  "content_type": "image/png",
  "size_bytes": 48213,
  "sha256": "9f2c1b7e4a0d3c5b8e6f1a2d3c4b5e6f70819a2b3c4d5e6f70819a2b3c4d5e6f",
  "technique": "lsb_statistical_analysis",
  "status": "sospechosos",
  "indicators": {
    "anomaly_score": 0.82,
    "threshold": 0.75,
    "chi_square_pvalue": 2.1e-7,
    "lsb_ones_ratio": 0.5003
  },
  "action": "cuarentena",
  "limitations": "Resultado indicativo, no concluyente. Un indicio no prueba la existencia de datos ocultos.",
  "created_at": "2026-11-02T19:40:00Z"
}
```

| Campo | Tipo | Regla |
|---|---|---|
| `analysis_id` | UUID v4 | PK del registro |
| `user_id` | UUID | `sub` del solicitante (no se recibe del cliente) |
| `filename` | string | Nombre original saneado (sin rutas, sin control chars, ≤ 255) |
| `content_type` | string | Tipo canónico detectado (`image/png` o `image/bmp`) |
| `size_bytes` | integer | > 0 |
| `sha256` | string | 64 hex en minúsculas, del archivo recibido |
| `technique` | string | `lsb_statistical_analysis` |
| `status` | enum | `sin_indicios` \| `sospechosos` \| `no_concluyentes` \| `error` |
| `indicators` | objeto | `anomaly_score` y `threshold` obligatorios; métricas extra numéricas permitidas |
| `action` | enum | `ninguna` \| `advertencia` \| `cuarentena` \| `rechazo` |
| `limitations` | string | Obligatorio, nunca vacío |
| `created_at` | ISO-8601 UTC | Momento del análisis |

Los valores del ejemplo son **ilustrativos**: los reales salen de las muestras y se documentan.

---

## 4. Clasificación y política

| `status` | Condición | `action` |
|---|---|---|
| `sin_indicios` | `anomaly_score < threshold` y LSB compatible con imagen natural | `ninguna` |
| `sospechosos` | `anomaly_score ≥ threshold` | `cuarentena` |
| `no_concluyentes` | Evidencia insuficiente: imagen demasiado pequeña, paleta reducida, compresión con pérdida, indicadores contradictorios | `advertencia` |
| `error` | Fallo controlado durante el análisis (archivo que decodifica pero no es procesable) | `rechazo` |

`no_concluyentes` es obligatorio: evita presentar un resultado débil como definitivo.
El umbral sale de `STEGO_LSB_ANOMALY_THRESHOLD` y su valor final debe justificarse con las métricas de
las muestras (informe, criterio 5).

---

## 5. Persistencia (base `stego`, esquema `stego`)

Sin claves foráneas hacia `auth`: son bases distintas y el acoplamiento está prohibido a propósito.
`user_id` es una **referencia lógica**, verificada con AUTH, no un FK.

Script ejecutable: [`db/stego/001_init.sql`](../../db/stego/001_init.sql). Tabla única
`stego.analyses` con las columnas del §3 y `CHECK` sobre `status`, `action`, formato de `sha256`,
tamaño positivo y `limitations` no vacío.

| Columna | Origen |
|---|---|
| `analysis_id` | generado por STEGO (UUID v4) |
| `user_id` | `sub` de la decisión de AUTH |
| `filename` | nombre original saneado |
| `stored_path` | ruta en cuarentena; no se expone |
| `sha256`, `content_type`, `size_bytes` | del archivo recibido |
| `technique`, `status`, `indicators`, `action`, `limitations` | resultado del analizador |
| `created_at` | UTC |

`stored_path` nunca se devuelve en la API ni se expone como URL pública.

---

## 6. Muestras obligatorias

| Muestra | Descripción | Uso |
|---|---|---|
| `sample-clean.png` | PNG generado sin datos ocultos | Esperado `sin_indicios` |
| `sample-lsb.png` | Misma imagen con carga LSB conocida (mensaje u otro archivo embebido) | Esperado `sospechosos` |
| `sample-clean.bmp` | BMP limpio | Demuestra soporte de formato |
| `sample-corrupt.png` | PNG truncado | `422 IMAGE_UNPROCESSABLE` |
| `sample-fake.png` | Archivo con extensión `.png` pero firma distinta (p. ej. PDF renombrado) | `415 FILE_SIGNATURE_MISMATCH` |
| `sample-huge.png` | PNG válido por encima de `STEGO_MAX_UPLOAD_BYTES` | `413 PAYLOAD_TOO_LARGE` |

Los scripts que las generan se versionan; nada de muestras descargadas sin trazabilidad.

---

## 7. Aceptación (T09, T10, T11)

- [ ] Imagen limpia y su versión con carga LSB producen clasificaciones distintas y **reales**.
- [ ] El JSON de respuesta valida contra `analysis-result.schema.json`.
- [ ] `sha256` del archivo coincide con `sha256sum` calculado fuera del servicio.
- [ ] Archivo corrupto y archivo con firma falsa se rechazan sin crear registro en `stego.analyses`.
- [ ] Exceder el tamaño devuelve `413`.
- [ ] Un análisis de otro usuario devuelve `403 RESULT_FORBIDDEN`; un id inexistente, `404`.
- [ ] Ningún archivo subido es accesible por HTTP público.
- [ ] Los logs del análisis no incluyen el contenido del archivo ni rutas internas completas.
