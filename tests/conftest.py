import os
import uuid

import httpx
import pytest

AUTH_BASE_URL = os.environ.get("AUTH_BASE_URL", "http://auth:8080")
STEGO_BASE_URL = os.environ.get("STEGO_BASE_URL", "http://stego:8081")
ADMIN_IDENTIFIER = os.environ.get("TEST_ADMIN_IDENTIFIER", "admin")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "AdminSegura2026!")
SERVICE_CLIENT_ID = os.environ.get("STEGO_SERVICE_CLIENT_ID", "stego")
SERVICE_CLIENT_SECRET = os.environ.get("STEGO_SERVICE_CLIENT_SECRET", "cambiame-cliente-stego")


@pytest.fixture(scope="session")
def auth() -> httpx.Client:
    with httpx.Client(base_url=AUTH_BASE_URL, timeout=10.0) as client:
        yield client


@pytest.fixture(scope="session")
def stego() -> httpx.Client:
    with httpx.Client(base_url=STEGO_BASE_URL, timeout=20.0) as client:
        yield client


@pytest.fixture(scope="session")
def admin_token(auth: httpx.Client) -> str:
    response = auth.post(
        "/api/v1/auth/login",
        json={"identifier": ADMIN_IDENTIFIER, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def service_token(auth: httpx.Client) -> str:
    response = auth.post(
        "/internal/service-token",
        json={"client_id": SERVICE_CLIENT_ID, "client_secret": SERVICE_CLIENT_SECRET},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def role_ids(auth: httpx.Client, admin_headers: dict[str, str]) -> dict[str, str]:
    response = auth.get("/api/v1/roles", params={"limit": 100}, headers=admin_headers)
    assert response.status_code == 200, response.text
    return {role["name"]: role["id"] for role in response.json()["items"]}


@pytest.fixture(scope="session")
def analyst_user(auth: httpx.Client, admin_headers: dict[str, str], role_ids: dict[str, str]) -> dict:
    suffix = uuid.uuid4().hex[:8]
    password = "AnalistaSegura2026!"
    created = auth.post(
        "/api/v1/users",
        json={
            "username": f"analista_{suffix}",
            "email": f"analista_{suffix}@espe.edu.ec",
            "password": password,
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    user = created.json()
    assignment = auth.post(
        "/api/v1/user-roles",
        json={"user_id": user["id"], "role_id": role_ids["ANALYST"]},
        headers=admin_headers,
    )
    assert assignment.status_code == 201, assignment.text
    token = auth.post(
        "/api/v1/auth/login", json={"identifier": user["username"], "password": password}
    ).json()["access_token"]
    return {**user, "assignment_id": assignment.json()["id"], "token": token, "password": password}
