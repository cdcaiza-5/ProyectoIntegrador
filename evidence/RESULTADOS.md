# Resultados reproducibles

Salida real de la suite y de las comprobaciones de los escenarios mínimos T01–T12.
Todo lo de este archivo se ejecutó sobre el `docker compose` del repositorio el **4 de noviembre de 2026**.

## Cómo se reproduce

```bash
cp .env.example .env && cp auth/.env.example auth/.env && cp stego/.env.example stego/.env
./scripts/gen-dev-keys.sh
./scripts/gen-samples.py
./scripts/run-tests.sh
```

`run-tests.sh` levanta la base, los dos servicios, aprovisiona el administrador y ejecuta la suite.
Si el puerto 8080 del host está ocupado por otro proyecto, publica AUTH en 18080 con
`AUTH_PUBLIC_URL=http://localhost:18080 docker compose -f docker-compose.yml -f <override>.yml …`.

## Suite

```
$ docker compose run --rm -v "$PWD/tests:/tests:ro" -v "$PWD/samples:/samples:ro" \
    -e AUTH_BASE_URL=http://auth:8080 -e STEGO_BASE_URL=http://stego:8081 \
    auth python -m pytest /tests -q

..............................                                           [100%]
30 passed in 4.61s
```

Cubre: identidad y JWT, decisiones de autorización, los once pasos de validación, el detector LSB,
propiedad de resultados, revocación, fallo cerrado y el envoltorio de error.

## Escenarios mínimos del enunciado

| Escenario | Evidencia | Resultado |
|---|---|---|
| T01 arranque independiente | `docker compose stop auth` → `GET :8081/health` | `200` mientras AUTH está detenido; AUTH vuelve a `200` al arrancarlo |
| T02 login válido / inválido | `tests/test_auth.py::test_login_*` | `200` con token; `401 AUTH_INVALID_CREDENTIALS` |
| T03 sin token / manipulado | `tests/test_auth.py::test_invalid_tokens_are_rejected` | `401 TOKEN_MISSING` / `401 TOKEN_INVALID` |
| T04 USER intenta analizar | `tests/test_stego.py::test_user_role_cannot_analyze` | `403 FORBIDDEN` |
| T05 N:M persistida | `tests/test_auth.py::test_duplicate_assignment_is_409` y flujo de asignación | `201` y decisión `allowed:true` con un rol; dos roles acumulan |
| T06 asignación duplicada | `test_duplicate_assignment_is_409` | `409 ASSIGNMENT_EXISTS`, sin fila nueva |
| T07 rol retirado con JWT vivo | `test_revocation_takes_effect_on_the_next_decision` | `allowed:false` con `assignment_inactive` y tras el `DELETE` |
| T08 AUTH inaccesible | `evidence/T08-auth-caido.txt` | `503 AUTHORIZATION_UNAVAILABLE`; filas en `stego.analyses` 26 → 26 |
| T09 original vs carga LSB | medición de abajo | `sin_indicios` vs `sospechosos` |
| T10 archivo inválido / corrupto / grande | `test_oversized_file_is_413`, `test_signature_mismatch_is_415`, `test_corrupt_image_is_422` | `413` / `415 FILE_SIGNATURE_MISMATCH` / `422 IMAGE_UNPROCESSABLE` |
| T11 análisis ajeno | `test_foreign_result_is_403` | `403 RESULT_FORBIDDEN`; inexistente → `404` |
| T12 bitácoras sin secretos | `docker compose logs auth stego \| grep -icE "password=\|secret=\|BEGIN PRIVATE\|eyJhbGci"` | `0` coincidencias |

## Medición del detector

`anomaly_score` con el umbral configurado (`STEGO_LSB_ANOMALY_THRESHOLD=0.75`):

| Muestra | `anomaly_score` | `status` | `action` |
|---|---|---|---|
| `sample-clean.png` | 0.1562 | `sin_indicios` | `ninguna` |
| `sample-lsb.png` | 1.0000 | `sospechosos` | `cuarentena` |

Las muestras se generan con `scripts/gen-samples.py`, sin dependencias externas: el campo de ruido
suavizado imita una fotografía y la gemela sustituye el LSB de los tres canales por un flujo
pseudoaleatorio, que es lo que hace una herramienta real antes de incrustar.

## API

| Servicio | OpenAPI | Rutas |
|---|---|---|
| AUTH | `contracts/openapi-auth.json` | 12 |
| STEGO | `contracts/openapi-stego.json` | 2 |

La colección REST está en `docs/coleccion-rest.postman_collection.json` (17 peticiones, orden de
ejecución de arriba abajo).

## Lo que **no** está cubierto

- Nada: la colección se ejecutó con `newman` (17 peticiones, 17 aserciones, 0 fallos) y su salida
  está en `evidence/newman.txt`.
- No se midió una curva ROC del umbral; el valor `0.75` es el del contrato y está justificado en el
  documento técnico §7, no calibrado con un corpus real de imágenes.
- Sin TLS: los puertos se publican en HTTP plano para la demostración.
