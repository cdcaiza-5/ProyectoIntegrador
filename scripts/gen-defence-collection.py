#!/usr/bin/env python3
"""Genera la colección de sustentación: un folder por cada paso del enunciado.

A diferencia de la colección de pruebas, esta sigue el orden exacto que el PDF
exige en §3 y cada aserción comprueba el resultado que hay que mostrar en vivo.
"""

import json
from pathlib import Path

AUTH = "{{base_url_auth}}"
STEGO = "{{base_url_stego}}"

def req(name, method, url, *, body=None, form=None, headers=None, tests=None, desc=""):
    request = {
        "method": method,
        "header": [{"key": k, "value": v} for k, v in (headers or {}).items()],
        "url": url,
    }
    if body is not None:
        request["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2),
                           "options": {"raw": {"language": "json"}}}
    if form is not None:
        request["body"] = {"mode": "formdata",
                           "formdata": [{"key": "file", "type": "file", "src": form}]}
    if desc:
        request["description"] = desc
    item = {"name": name, "request": request}
    if tests:
        item["event"] = [{"listen": "test", "script": {"type": "text/javascript", "exec": tests}}]
    return item

def bearer(var):
    return {"Authorization": "Bearer " + var}

def expect(status, extra=None):
    lines = [f"pm.test('HTTP {status}', () => pm.response.to.have.status({status}));",
             "const b = pm.response.code === 204 ? {} : pm.response.json();"]
    return lines + (extra or [])

folders = []

# ---------------------------------------------------------------- Paso 1
folders.append({
    "name": "Paso 1 · Cada servicio responde desde su propia API",
    "description": "Dos procesos, dos imágenes, dos puertos. Ninguno depende del otro para arrancar.",
    "item": [
        req("1.1 · health de AUTH", "GET", AUTH + "/health",
            tests=expect(200, ["pm.test('se identifica como auth', () => pm.expect(b.service).to.eql('auth'));"])),
        req("1.2 · health de STEGO", "GET", STEGO + "/health",
            tests=expect(200, ["pm.test('se identifica como stego', () => pm.expect(b.service).to.eql('stego'));"])),
        req("1.3 · JWKS de AUTH (solo material público)", "GET", AUTH + "/.well-known/jwks.json",
            tests=expect(200, [
                "pm.test('expone una clave RSA con kid', () => {",
                "  pm.expect(b.keys[0].kty).to.eql('RSA'); pm.expect(b.keys[0].kid).to.be.a('string');",
                "});",
                "pm.test('no expone la parte privada', () => pm.expect(b.keys[0]).to.not.have.property('d'));",
            ])),
    ],
})

# ---------------------------------------------------------------- Paso 2
folders.append({
    "name": "Paso 2 · Un usuario con dos roles",
    "description": "ana recibe ANALYST y USER; el perfil demuestra que la N:M persiste.",
    "item": [
        req("2.1 · login del ADMIN", "POST", AUTH + "/api/v1/auth/login",
            body={"identifier": "{{admin_identifier}}", "password": "{{admin_password}}"},
            headers={"Content-Type": "application/json"},
            tests=expect(200, ["pm.collectionVariables.set('admin_token', b.access_token);"])),
        req("2.2 · roles disponibles", "GET", AUTH + "/api/v1/roles?limit=100",
            headers=bearer("{{admin_token}}"),
            tests=expect(200, [
                "pm.collectionVariables.set('role_analyst', b.items.find(r => r.name === 'ANALYST').id);",
                "pm.collectionVariables.set('role_user', b.items.find(r => r.name === 'USER').id);",
            ])),
        req("2.3 · crear a ana", "POST", AUTH + "/api/v1/users",
            body={"username": "ana.{{$timestamp}}", "email": "ana.{{$timestamp}}@espe.edu.ec",
                  "password": "AnaSegura2026!"},
            headers={"Content-Type": "application/json", **bearer("{{admin_token}}")},
            tests=expect(201, [
                "pm.collectionVariables.set('ana_id', b.id);",
                "pm.collectionVariables.set('ana_user', b.username);",
            ])),
        req("2.4 · asignar ANALYST", "POST", AUTH + "/api/v1/user-roles",
            body={"user_id": "{{ana_id}}", "role_id": "{{role_analyst}}"},
            headers={"Content-Type": "application/json", **bearer("{{admin_token}}")},
            tests=expect(201)),
        req("2.5 · asignar USER", "POST", AUTH + "/api/v1/user-roles",
            body={"user_id": "{{ana_id}}", "role_id": "{{role_user}}"},
            headers={"Content-Type": "application/json", **bearer("{{admin_token}}")},
            tests=expect(201)),
        req("2.6 · login de ana", "POST", AUTH + "/api/v1/auth/login",
            body={"identifier": "{{ana_user}}", "password": "AnaSegura2026!"},
            headers={"Content-Type": "application/json"},
            tests=expect(200, ["pm.collectionVariables.set('ana_token', b.access_token);"])),
        req("2.7 · el perfil muestra los dos roles", "GET", AUTH + "/api/v1/auth/profile",
            headers=bearer("{{ana_token}}"),
            tests=expect(200, [
                "pm.test('ana acumula ANALYST y USER', () => {",
                "  pm.expect(b.roles).to.include('ANALYST'); pm.expect(b.roles).to.include('USER');",
                "});",
            ])),
    ],
})

# ---------------------------------------------------------------- Paso 3
folders.append({
    "name": "Paso 3 · Un rol asignado a dos usuarios",
    "description": "beto recibe el mismo ANALYST que ana.",
    "item": [
        req("3.1 · crear a beto", "POST", AUTH + "/api/v1/users",
            body={"username": "beto.{{$timestamp}}", "email": "beto.{{$timestamp}}@espe.edu.ec",
                  "password": "BetoSegura2026!"},
            headers={"Content-Type": "application/json", **bearer("{{admin_token}}")},
            tests=expect(201, [
                "pm.collectionVariables.set('beto_id', b.id);",
                "pm.collectionVariables.set('beto_user', b.username);",
            ])),
        req("3.2 · el mismo ANALYST para beto", "POST", AUTH + "/api/v1/user-roles",
            body={"user_id": "{{beto_id}}", "role_id": "{{role_analyst}}"},
            headers={"Content-Type": "application/json", **bearer("{{admin_token}}")},
            tests=expect(201, ["pm.collectionVariables.set('beto_asg', b.id);"])),
        req("3.3 · login de beto", "POST", AUTH + "/api/v1/auth/login",
            body={"identifier": "{{beto_user}}", "password": "BetoSegura2026!"},
            headers={"Content-Type": "application/json"},
            tests=expect(200, ["pm.collectionVariables.set('beto_token', b.access_token);"])),
    ],
})

# ---------------------------------------------------------------- Paso 4
folders.append({
    "name": "Paso 4 · El JWT de AUTH sirve contra STEGO",
    "description": "Mismo token, otro servicio. STEGO no conoce la base de AUTH: valida por JWKS y pide la decisión.",
    "item": [
        req("4.1 · analyze con el token de ana", "POST", STEGO + "/api/v1/steganography/analyze",
            form="samples/sample-clean.png", headers=bearer("{{ana_token}}"),
            tests=expect(201, ["pm.collectionVariables.set('analysis_id', b.analysis_id);"])),
        req("4.2 · leer el resultado por id", "GET", STEGO + "/api/v1/steganography/results/{{analysis_id}}",
            headers=bearer("{{ana_token}}"), tests=expect(200)),
    ],
})

# ---------------------------------------------------------------- Paso 5
folders.append({
    "name": "Paso 5 · Denegaciones: sin token, token inválido, sin privilegios",
    "description": "401 = no sé quién eres. 403 = sé quién eres y no puedes. No se mezclan.",
    "item": [
        req("5.1 · sin token → 401", "POST", STEGO + "/api/v1/steganography/analyze",
            form="samples/sample-clean.png",
            tests=expect(401, ["pm.test('TOKEN_MISSING', () => pm.expect(b.error.code).to.eql('TOKEN_MISSING'));"])),
        req("5.2 · token manipulado → 401", "POST", STEGO + "/api/v1/steganography/analyze",
            form="samples/sample-clean.png", headers={"Authorization": "Bearer no.es.un.jwt"},
            tests=expect(401, ["pm.test('TOKEN_INVALID', () => pm.expect(b.error.code).to.eql('TOKEN_INVALID'));"])),
        req("5.3 · crear a carla, sin ningún rol", "POST", AUTH + "/api/v1/users",
            body={"username": "carla.{{$timestamp}}", "email": "carla.{{$timestamp}}@espe.edu.ec",
                  "password": "CarlaSegura2026!"},
            headers={"Content-Type": "application/json", **bearer("{{admin_token}}")},
            tests=expect(201, ["pm.collectionVariables.set('carla_user', b.username);"])),
        req("5.4 · login de carla", "POST", AUTH + "/api/v1/auth/login",
            body={"identifier": "{{carla_user}}", "password": "CarlaSegura2026!"},
            headers={"Content-Type": "application/json"},
            tests=expect(200, ["pm.collectionVariables.set('carla_token', b.access_token);"])),
        req("5.5 · autenticada pero sin rol → 403", "POST", STEGO + "/api/v1/steganography/analyze",
            form="samples/sample-clean.png", headers=bearer("{{carla_token}}"),
            tests=expect(403, ["pm.test('FORBIDDEN', () => pm.expect(b.error.code).to.eql('FORBIDDEN'));"])),
    ],
})

# ---------------------------------------------------------------- Paso 6
folders.append({
    "name": "Paso 6 · Retirar el rol con el mismo JWT todavía vigente",
    "description": "El token no lleva roles: AUTH los relee en cada petición. Es la prueba de que la revocación funciona sin esperar a que expire.",
    "item": [
        req("6.1 · beto analiza (tiene ANALYST)", "POST", STEGO + "/api/v1/steganography/analyze",
            form="samples/sample-clean.png", headers=bearer("{{beto_token}}"), tests=expect(201)),
        req("6.2 · DELETE de la asignación", "DELETE", AUTH + "/api/v1/user-roles/{{beto_asg}}",
            headers=bearer("{{admin_token}}"), tests=expect(204)),
        req("6.3 · el MISMO JWT ahora → 403", "POST", STEGO + "/api/v1/steganography/analyze",
            form="samples/sample-clean.png", headers=bearer("{{beto_token}}"),
            tests=expect(403, [
                "pm.test('el token no expiró: sigue vigente', () => {",
                "  const p = JSON.parse(atob(pm.collectionVariables.get('beto_token').split('.')[1]));",
                "  pm.expect(p.exp * 1000).to.be.greaterThan(Date.now());",
                "});",
            ])),
    ],
})

# ---------------------------------------------------------------- Paso 7
folders.append({
    "name": "Paso 7 · AUTH caído (manual)",
    "description": (
        "Este paso no puede automatizarse dentro de una corrida: hay que parar un contenedor a mitad. "
        "En una terminal, con el stack levantado:\n\n"
        "    docker compose stop auth\n"
        "    curl -i -X POST http://localhost:8081/api/v1/steganography/analyze \\\n"
        "      -H 'Authorization: Bearer <token de ana>' -F 'file=@samples/sample-clean.png'\n"
        "    docker compose start auth\n\n"
        "Esperado: 503 AUTHORIZATION_UNAVAILABLE y ninguna fila nueva en stego.analyses."
    ),
    "item": [],
})

# ---------------------------------------------------------------- Paso 8
folders.append({
    "name": "Paso 8 · Imagen de referencia frente a imagen con carga LSB",
    "description": "El detector separa una imagen natural de su gemela con el LSB sustituido.",
    "item": [
        req("8.1 · imagen de referencia", "POST", STEGO + "/api/v1/steganography/analyze",
            form="samples/sample-clean.png", headers=bearer("{{ana_token}}"),
            tests=expect(201, [
                "pm.collectionVariables.set('clean_score', b.indicators.anomaly_score);",
                "pm.test('sin indicios', () => pm.expect(['sin_indicios','no_concluyentes']).to.include(b.status));",
                "pm.test('limitations no está vacío', () => pm.expect(b.limitations.trim()).to.not.be.empty);",
            ])),
        req("8.2 · imagen con carga LSB", "POST", STEGO + "/api/v1/steganography/analyze",
            form="samples/sample-lsb.png", headers=bearer("{{ana_token}}"),
            tests=expect(201, [
                "pm.test('marcada como sospechosa', () => pm.expect(b.status).to.eql('sospechosos'));",
                "pm.test('acción de cuarentena', () => pm.expect(b.action).to.eql('cuarentena'));",
                "pm.test('puntúa más alto que la de referencia', () =>",
                "  pm.expect(b.indicators.anomaly_score).to.be.greaterThan(pm.collectionVariables.get('clean_score')));",
            ])),
    ],
})

collection = {
    "info": {
        "name": "Sustentación — Backend V1 (AUTH + STEGO)",
        "description": (
            "Un folder por cada paso que exige el enunciado (§3), en su orden.\n\n"
            "Ejecutar desde la raíz del repositorio: `newman run docs/coleccion-sustentacion.postman_collection.json`\n\n"
            "El paso 7 es el único manual: exige parar AUTH a mitad de la demostración."
        ),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "variable": [
        {"key": "base_url_auth", "value": "http://localhost:8080"},
        {"key": "base_url_stego", "value": "http://localhost:8081"},
        {"key": "admin_identifier", "value": "admin"},
        {"key": "admin_password", "value": "AdminSegura2026!"},
        {"key": "admin_token", "value": ""},
        {"key": "ana_token", "value": ""},
        {"key": "beto_token", "value": ""},
        {"key": "carla_token", "value": ""},
    ],
    "item": folders,
}

Path("docs/coleccion-sustentacion.postman_collection.json").write_text(
    json.dumps(collection, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
total = sum(len(f["item"]) for f in folders)
print(f"colección de sustentación: {len(folders)} pasos, {total} peticiones")
