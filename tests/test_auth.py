import uuid

import httpx
import pytest


def test_health_has_no_sensitive_data(auth: httpx.Client) -> None:
    response = auth.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "auth"}


def test_jwks_exposes_only_the_public_key(auth: httpx.Client) -> None:
    response = auth.get("/.well-known/jwks.json")
    assert response.status_code == 200
    key = response.json()["keys"][0]
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    assert key["kid"]
    assert "d" not in key


def test_login_returns_a_token_without_roles_inside(auth: httpx.Client, admin_token: str) -> None:
    import jwt

    claims = jwt.decode(admin_token, options={"verify_signature": False})
    assert claims["token_use"] == "access"
    assert claims["aud"] == ["auth-api", "stego-api"]
    assert "roles" not in claims
    assert "permissions" not in claims


def test_login_with_wrong_password_is_401(auth: httpx.Client) -> None:
    response = auth.post(
        "/api/v1/auth/login", json={"identifier": "admin", "password": "clave-incorrecta-123"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"


def test_login_with_unknown_user_is_401_without_revealing_existence(auth: httpx.Client) -> None:
    response = auth.post(
        "/api/v1/auth/login",
        json={"identifier": "no-existe-esta-persona", "password": "clave-inventada-123"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"


def test_profile_returns_active_roles(
    auth: httpx.Client, admin_headers: dict[str, str]
) -> None:
    response = auth.get("/api/v1/auth/profile", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["roles"] == ["ADMIN"]


def test_admin_creates_user_and_duplicates_are_rejected(
    auth: httpx.Client, admin_headers: dict[str, str]
) -> None:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "username": f"usuario_{suffix}",
        "email": f"usuario_{suffix}@espe.edu.ec",
        "password": "UsuarioSegura2026!",
    }
    created = auth.post("/api/v1/users", json=payload, headers=admin_headers)
    assert created.status_code == 201
    assert "password" not in created.json()
    assert "password_hash" not in created.json()

    duplicated = auth.post("/api/v1/users", json=payload, headers=admin_headers)
    assert duplicated.status_code == 409
    assert duplicated.json()["error"]["code"] == "USER_EXISTS"


def test_analyst_cannot_list_users(
    auth: httpx.Client, analyst_user: dict
) -> None:
    response = auth.get(
        "/api/v1/users", headers={"Authorization": f"Bearer {analyst_user['token']}"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_duplicate_assignment_is_409(
    auth: httpx.Client, admin_headers: dict[str, str], analyst_user: dict, role_ids: dict[str, str]
) -> None:
    response = auth.post(
        "/api/v1/user-roles",
        json={"user_id": analyst_user["id"], "role_id": role_ids["ANALYST"]},
        headers=admin_headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ASSIGNMENT_EXISTS"


def test_authorization_decision_has_exactly_nine_fields(
    auth: httpx.Client, service_token: str, analyst_user: dict
) -> None:
    response = auth.post(
        "/internal/authorization/check",
        json={
            "subject_token": analyst_user["token"],
            "action": "steganography.analyze",
            "resource_id": None,
        },
        headers={"Authorization": f"Bearer {service_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "decision_id",
        "subject_id",
        "action",
        "resource_id",
        "allowed",
        "reason",
        "roles",
        "decided_at",
        "decision_ttl_seconds",
    }
    assert body["allowed"] is True
    assert body["reason"] == "active_role_grants_permission"
    assert body["decision_ttl_seconds"] == 30


def test_user_without_role_cannot_analyze(
    auth: httpx.Client, service_token: str, admin_headers: dict[str, str]
) -> None:
    suffix = uuid.uuid4().hex[:8]
    password = "SinRolSegura2026!"
    user = auth.post(
        "/api/v1/users",
        json={
            "username": f"sinrol_{suffix}",
            "email": f"sinrol_{suffix}@espe.edu.ec",
            "password": password,
        },
        headers=admin_headers,
    ).json()
    token = auth.post(
        "/api/v1/auth/login", json={"identifier": user["username"], "password": password}
    ).json()["access_token"]

    decision = auth.post(
        "/internal/authorization/check",
        json={"subject_token": token, "action": "steganography.analyze", "resource_id": None},
        headers={"Authorization": f"Bearer {service_token}"},
    ).json()
    assert decision["allowed"] is False


def test_a_user_token_is_rejected_as_service_token(
    auth: httpx.Client, analyst_user: dict
) -> None:
    response = auth.post(
        "/internal/authorization/check",
        json={
            "subject_token": analyst_user["token"],
            "action": "steganography.analyze",
            "resource_id": None,
        },
        headers={"Authorization": f"Bearer {analyst_user['token']}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SERVICE_AUTH_FAILED"


def test_unknown_action_is_denied_not_errored(
    auth: httpx.Client, service_token: str, analyst_user: dict
) -> None:
    response = auth.post(
        "/internal/authorization/check",
        json={"subject_token": analyst_user["token"], "action": "accion.inventada", "resource_id": None},
        headers={"Authorization": f"Bearer {service_token}"},
    )
    assert response.status_code == 200
    assert response.json()["allowed"] is False
    assert response.json()["reason"] == "unknown_action"


def test_revocation_takes_effect_on_the_next_decision(
    auth: httpx.Client,
    admin_headers: dict[str, str],
    service_token: str,
    role_ids: dict[str, str],
) -> None:
    suffix = uuid.uuid4().hex[:8]
    password = "RevocableSegura2026!"
    user = auth.post(
        "/api/v1/users",
        json={
            "username": f"revocable_{suffix}",
            "email": f"revocable_{suffix}@espe.edu.ec",
            "password": password,
        },
        headers=admin_headers,
    ).json()
    assignment = auth.post(
        "/api/v1/user-roles",
        json={"user_id": user["id"], "role_id": role_ids["ANALYST"]},
        headers=admin_headers,
    ).json()
    token = auth.post(
        "/api/v1/auth/login", json={"identifier": user["username"], "password": password}
    ).json()["access_token"]

    def decision() -> dict:
        return auth.post(
            "/internal/authorization/check",
            json={"subject_token": token, "action": "steganography.analyze", "resource_id": None},
            headers={"Authorization": f"Bearer {service_token}"},
        ).json()

    assert decision()["allowed"] is True

    deactivated = auth.patch(
        f"/api/v1/user-roles/{assignment['id']}", json={"status": "inactive"}, headers=admin_headers
    )
    assert deactivated.status_code == 200
    denied = decision()
    assert denied["allowed"] is False
    assert denied["reason"] == "assignment_inactive"

    auth.patch(
        f"/api/v1/user-roles/{assignment['id']}", json={"status": "active"}, headers=admin_headers
    )
    assert decision()["allowed"] is True

    removed = auth.delete(f"/api/v1/user-roles/{assignment['id']}", headers=admin_headers)
    assert removed.status_code == 204
    assert decision()["allowed"] is False


def test_logout_revokes_the_token(
    auth: httpx.Client, admin_headers: dict[str, str], role_ids: dict[str, str]
) -> None:
    suffix = uuid.uuid4().hex[:8]
    password = "LogoutSegura2026!"
    created = auth.post(
        "/api/v1/users",
        json={
            "username": f"logout_{suffix}",
            "email": f"logout_{suffix}@espe.edu.ec",
            "password": password,
        },
        headers=admin_headers,
    )
    auth.post(
        "/api/v1/user-roles",
        json={"user_id": created.json()["id"], "role_id": role_ids["USER"]},
        headers=admin_headers,
    )
    token = auth.post(
        "/api/v1/auth/login", json={"identifier": f"logout_{suffix}", "password": password}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert auth.get("/api/v1/auth/profile", headers=headers).status_code == 200
    assert auth.post("/api/v1/auth/logout", headers=headers).status_code == 204
    revoked = auth.get("/api/v1/auth/profile", headers=headers)
    assert revoked.status_code == 401
    assert revoked.json()["error"]["code"] == "TOKEN_REVOKED"


def test_invalid_tokens_are_rejected(auth: httpx.Client) -> None:
    missing = auth.get("/api/v1/auth/profile")
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "TOKEN_MISSING"

    tampered = auth.get(
        "/api/v1/auth/profile", headers={"Authorization": "Bearer esto.no.es.un.jwt"}
    )
    assert tampered.status_code == 401
    assert tampered.json()["error"]["code"] == "TOKEN_INVALID"


def test_error_envelope_shape(auth: httpx.Client) -> None:
    response = auth.get("/api/v1/auth/profile")
    body = response.json()["error"]
    assert set(body) >= {"code", "message", "request_id", "timestamp"}
    assert not any(part in str(body).lower() for part in ("traceback", "sql", "password_hash"))


def test_request_id_is_echoed(auth: httpx.Client) -> None:
    response = auth.get("/health", headers={"X-Request-Id": "prueba.abc-123"})
    assert response.headers["x-request-id"] == "prueba.abc-123"

    generated = auth.get("/health", headers={"X-Request-Id": "no vale!"})
    assert generated.headers["x-request-id"] != "no vale!"
