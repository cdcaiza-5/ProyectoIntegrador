# Documentación técnica — entregable separado

Este archivo es una **guía de trabajo**, no el entregable. La documentación técnica evaluable es un
documento **aparte** (§3 del enunciado: «La documentación técnica deberá incorporar…»).

Los `.md` del repositorio sirven para construir y para que el equipo se coordine. El documento técnico
se redacta con ese material y se entrega por separado.

---

## Índice obligatorio

Los nueve puntos salen del §3 del enunciado. Ninguno es opcional y no hay que añadir otros para cumplir.

| # | El enunciado pide | ¿Existe en el repo? |
|---|---|---|
| 1 | Diagrama de arquitectura con límites de confianza | ⛔ Hay que crearlo |
| 2 | Diagrama entidad–relación de la N:M | ⛔ Hay que crearlo |
| 3 | Explicación de JWT, RBAC y verificación de roles vigentes | ✅ Base en contratos 1 y 2 |
| 4 | Matriz de roles y permisos | ✅ Base en contrato 4 |
| 5 | Especificaciones OpenAPI de ambos servicios | ⛔ Se genera en la actividad 10 |
| 6 | Justificación del método esteganográfico | ⛔ Hay que redactarlo |
| 7 | Matriz de activos, amenazas, riesgos y controles | ⛔ Hay que crearla |
| 8 | Resultados de pruebas unitarias, funcionales, de seguridad e integración | ⛔ Salen de la actividad 12 |
| 9 | Justificación de la selección tecnológica (§2.1) | ⛔ Hay que redactarlo |

---

## Qué debe contener cada punto

### 1. Diagrama de arquitectura con límites de confianza

- AUTH y STEGO como procesos separados, cada uno con su configuración y sus endpoints.
- **Límites de confianza explícitos**: cliente externo → AUTH; cliente externo → STEGO; STEGO → AUTH por
  el canal interno; servicios → base de datos.
- Flujo numerado: login → JWT → STEGO → `authorization/check` → análisis → resultado.
- Qué cruza cada frontera y con qué protección (token firmado, token de servicio, red interna).
- La base de datos y el volumen de archivos marcados como **infraestructura**, no como tercer servicio.

**Fuente:** contratos 2 y 7.

### 2. Diagrama entidad–relación

- `users`, `roles`, `user_roles` con PK, FK y el `UNIQUE(user_id, role_id)`.
- Cardinalidad N:M visible: un usuario varios roles, un rol varios usuarios.
- `status` en las tres tablas y su efecto sobre la autorización.
- `revoked_tokens` y `service_clients` si se incluyen, marcadas como auxiliares.

**Fuente:** contrato 5 y `db/auth/001_init.sql`.

### 3. Explicación de JWT, autorización RBAC y estrategia de roles vigentes

- Por qué un JWT válido **no** basta: identifica, no autoriza.
- Claims del token y por qué **no** lleva roles.
- Las ocho verificaciones del contrato 1.
- Cómo AUTH relee usuario, asignación y rol en **cada** decisión.
- Las tres condiciones simultáneas: `users.status`, `user_roles.status`, `roles.status`.
- Qué pasa al retirar o desactivar una asignación con el token aún vigente.
- Gestión de claves: privada solo en AUTH, pública por JWKS, rotación por `kid`.

**Fuente:** contratos 1 y 2.

### 4. Matriz de roles y permisos

- Doce acciones × tres roles, tal como está en el contrato 4.
- Las tres rutas internas o de infraestructura marcadas como no públicas.
- La regla de propiedad de recursos de `steganography.results.read`.

**Fuente:** contrato 4. Se puede copiar la tabla tal cual.

### 5. Especificaciones OpenAPI

- Un documento por servicio, exportado desde la aplicación en ejecución.
- El endpoint interno marcado como **solo servicio**, no público.
- Debe coincidir con lo que responde de verdad: es un punto fácil de penalizar.

**Fuente:** actividad 10.

### 6. Justificación del método esteganográfico

- Técnica elegida y **por qué** (análisis estadístico del LSB).
- Fórmulas y parámetros: umbral, métrica, qué se mide exactamente.
- Formatos soportados (PNG, BMP) y **por qué no** JPEG.
- Las cuatro clasificaciones y el criterio que separa cada una.
- Limitaciones explícitas: un resultado `sospechosos` es un indicio, no prueba.
- Resultados reales sobre la muestra limpia y la muestra con carga.

**Fuente:** contrato 6 y actividad 8.

### 7. Matriz de activos, amenazas, vulnerabilidades, riesgos y controles

El enunciado trae una tabla de referencia (Anexo E) que **debe adaptarse**, no copiarse. Mínimo, los
seis activos del Anexo E: credenciales, asignaciones N:M, JWT y claves, comunicación AUTH–STEGO,
archivos e imágenes, resultados y registros.

Para cada fila: activo · amenaza · vulnerabilidad · riesgo · control implementado · **a qué enfoque
responde**.

Y la vinculación explícita con:

- **Zero Trust** (§2.4: ningún servicio confía en el otro sin verificar, decisión por operación)
- **Secure by Design** (§2.1: separación de responsabilidades, mínimo privilegio)
- **Shift Left** (§2.4 y §3: pruebas de credenciales, autorización y archivos desde el diseño)
- **ISO/IEC 27001:2022** e **ISO/IEC 27034-1:2011** como referencia de principios

⚠️ Sin afirmar certificación ni cumplimiento integral. El enunciado lo dice dos veces.

### 8. Resultados de pruebas reproducibles

- Unitarias, funcionales, de seguridad e integración — las cuatro categorías nombradas.
- Evidencia de **T01 a T12**, cada una con su comando y su salida.
- Muestras de imagen: original, con carga LSB y las inválidas.
- Colección de solicitudes REST.
- Bitácoras de auditoría **depuradas** de contraseñas, claves y JWT completos.

**Fuente:** actividad 12.

### 9. Justificación de la selección tecnológica

El §2.1 no impone lenguaje ni framework, pero exige que la elección se justifique. Conviene argumentar:

- Un mismo lenguaje para ambos servicios reduce el esfuerzo de integración.
- Es el stack del microservicio de referencia del curso, así que las convenciones ya están validadas.
- FastAPI genera OpenAPI automáticamente, y el enunciado pide OpenAPI de ambos servicios.
- Ecosistema de imagen suficiente para el análisis LSB.
- La seguridad no depende del lenguaje: los controles están en el diseño y existen en cualquier stack.

**Fuente:** README, sección «Repositorios de referencia».

---

## Lo que **no** va en este documento

- Los contratos internos con su historial de versiones: son guías, no entregable.
- El tablero de tareas.
- El registro de decisiones y lo que quedó fuera de alcance, salvo la justificación tecnológica.

---

## Orden de redacción sugerido

Se puede avanzar sin esperar al código en 4, 6, 7 y 9. Los demás necesitan el sistema funcionando.

| Cuándo | Puntos |
|---|---|
| Ya | 4 (matriz, ya está), 6 (método elegido), 7 (riesgos), 9 (tecnología) |
| Al cerrar AUTH | 1, 2, 3 |
| Al cerrar STEGO | 5, 8 |
