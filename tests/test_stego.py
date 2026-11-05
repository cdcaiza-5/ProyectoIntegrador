import uuid
from pathlib import Path

import httpx
import pytest

SAMPLES = Path("/samples")
REQUIRED_FIELDS = {
    "analysis_id",
    "user_id",
    "filename",
    "content_type",
    "size_bytes",
    "sha256",
    "technique",
    "status",
    "indicators",
    "action",
    "limitations",
    "created_at",
}
STATUSES = {"sin_indicios", "sospechosos", "no_concluyentes", "error"}
ACTIONS = {"ninguna", "advertencia", "cuarentena", "rechazo"}


def _token(auth: httpx.Client, identifier: str, password: str) -> str:
    response = auth.post("/api/v1/auth/login", json={"identifier": identifier, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _user_with_role(
    auth: httpx.Client, admin_headers: dict[str, str], role_ids: dict[str, str], role: str
) -> tuple[dict, str]:
    suffix = uuid.uuid4().hex[:8]
    password = "AnalisisSegura2026!"
    user = auth.post(
        "/api/v1/users",
        json={
            "username": f"{role.lower()}_{suffix}",
            "email": f"{role.lower()}_{suffix}@espe.edu.ec",
            "password": password,
        },
        headers=admin_headers,
    ).json()
    auth.post(
        "/api/v1/user-roles",
        json={"user_id": user["id"], "role_id": role_ids[role]},
        headers=admin_headers,
    )
    return user, _token(auth, user["username"], password)


@pytest.fixture(scope="module")
def analyst(auth, admin_headers, role_ids) -> tuple[dict, str]:
    return _user_with_role(auth, admin_headers, role_ids, "ANALYST")


@pytest.fixture(scope="module")
def other_analyst(auth, admin_headers, role_ids) -> tuple[dict, str]:
    return _user_with_role(auth, admin_headers, role_ids, "ANALYST")


def _analyze(stego: httpx.Client, token: str, name: str, content_type: str = "image/png"):
    payload = (SAMPLES / name).read_bytes()
    return stego.post(
        "/api/v1/steganography/analyze",
        files={"file": (name, payload, content_type)},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_health(stego: httpx.Client) -> None:
    response = stego.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "stego"}


def test_analyze_without_token_is_401(stego: httpx.Client) -> None:
    response = stego.post(
        "/api/v1/steganography/analyze",
        files={"file": ("sample-clean.png", (SAMPLES / "sample-clean.png").read_bytes(), "image/png")},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_MISSING"


def test_user_role_cannot_analyze(stego: httpx.Client, auth, admin_headers, role_ids) -> None:
    _, token = _user_with_role(auth, admin_headers, role_ids, "USER")
    response = _analyze(stego, token, "sample-clean.png")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_oversized_file_is_413(stego: httpx.Client, analyst) -> None:
    response = _analyze(stego, analyst[1], "sample-huge.png")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_signature_mismatch_is_415(stego: httpx.Client, analyst) -> None:
    response = _analyze(stego, analyst[1], "sample-fake.png")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "FILE_SIGNATURE_MISMATCH"


def test_corrupt_image_is_422(stego: httpx.Client, analyst) -> None:
    response = _analyze(stego, analyst[1], "sample-corrupt.png")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "IMAGE_UNPROCESSABLE"


def test_clean_image_is_not_flagged(stego: httpx.Client, analyst) -> None:
    response = _analyze(stego, analyst[1], "sample-clean.png")
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == REQUIRED_FIELDS
    assert body["technique"] == "lsb_statistical_analysis"
    assert body["status"] in STATUSES
    assert body["action"] in ACTIONS
    assert body["limitations"].strip()
    assert body["status"] in {"sin_indicios", "no_concluyentes"}


def test_bmp_is_supported(stego: httpx.Client, analyst) -> None:
    response = _analyze(stego, analyst[1], "sample-clean.bmp", "image/bmp")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["content_type"] == "image/bmp"
    assert body["technique"] == "lsb_statistical_analysis"
    assert body["status"] in STATUSES


def test_bmp_declared_as_png_is_rejected(stego: httpx.Client, analyst) -> None:
    response = _analyze(stego, analyst[1], "sample-clean.bmp", "image/png")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "FILE_SIGNATURE_MISMATCH"


def test_lsb_image_is_flagged_and_differs_from_clean(stego: httpx.Client, analyst) -> None:
    clean = _analyze(stego, analyst[1], "sample-clean.png").json()
    loaded = _analyze(stego, analyst[1], "sample-lsb.png").json()
    assert loaded["status"] == "sospechosos"
    assert loaded["action"] == "cuarentena"
    assert loaded["indicators"]["anomaly_score"] > clean["indicators"]["anomaly_score"]


def test_result_is_readable_by_its_owner(stego: httpx.Client, analyst) -> None:
    created = _analyze(stego, analyst[1], "sample-clean.png").json()
    response = stego.get(
        f"/api/v1/steganography/results/{created['analysis_id']}",
        headers={"Authorization": f"Bearer {analyst[1]}"},
    )
    assert response.status_code == 200
    assert response.json()["analysis_id"] == created["analysis_id"]


def test_foreign_result_is_403(stego: httpx.Client, analyst, other_analyst) -> None:
    created = _analyze(stego, analyst[1], "sample-clean.png").json()
    response = stego.get(
        f"/api/v1/steganography/results/{created['analysis_id']}",
        headers={"Authorization": f"Bearer {other_analyst[1]}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "RESULT_FORBIDDEN"


def test_unknown_result_is_404(stego: httpx.Client, analyst) -> None:
    response = stego.get(
        f"/api/v1/steganography/results/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {analyst[1]}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESULT_NOT_FOUND"


def test_short_analyst_cannot_bypass_with_headers(stego: httpx.Client, auth, admin_headers, role_ids) -> None:
    _, token = _user_with_role(auth, admin_headers, role_ids, "USER")
    payload = (SAMPLES / "sample-clean.png").read_bytes()
    response = stego.post(
        "/api/v1/steganography/analyze",
        files={"file": ("sample-clean.png", payload, "image/png")},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Role": "ADMIN",
            "X-User-Id": "00000000-0000-4000-8000-000000000000",
        },
    )
    assert response.status_code == 403
