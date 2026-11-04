"""Pruebas de unidad de las piezas que no necesitan HTTP.

Se ejecutan en el contenedor del servicio que contiene el módulo, y cada bloque
se salta solo si ese módulo no está en la imagen: la de AUTH no tiene Pillow y
la de STEGO no tiene el código de identidad.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

# ----------------------------------------------------------------- AUTH


def test_password_hash_es_argon2id_y_verifica() -> None:
    security = pytest.importorskip("app.security")
    digest = security.hash_password("ClaveDePrueba2026!")
    assert digest.startswith("$argon2id$")
    assert security.verify_password("ClaveDePrueba2026!", digest) is True
    assert security.verify_password("otra-clave", digest) is False


def test_verificacion_contra_hash_ficticio_no_revienta() -> None:
    security = pytest.importorskip("app.security")
    assert security.verify_password("lo-que-sea", None) is False


def test_token_ida_y_vuelta() -> None:
    security = pytest.importorskip("app.security")
    subject = uuid.uuid4()
    token, jti, expires = security.issue_access_token(subject, "ana")
    claims = security.decode_token(token, "auth-api")

    assert claims["sub"] == str(subject)
    assert claims["jti"] == str(jti)
    assert claims["token_use"] == "access"
    assert claims["iss"] == "auth-service"
    assert set(claims["aud"]) == {"auth-api", "stego-api"}
    assert claims["exp"] - claims["iat"] == 900


def test_el_token_no_lleva_roles_ni_datos_personales() -> None:
    security = pytest.importorskip("app.security")
    token, _, _ = security.issue_access_token(uuid.uuid4(), "ana")
    claims = security.decode_token(token, "auth-api")
    for prohibido in ("roles", "permissions", "scope", "email", "password_hash"):
        assert prohibido not in claims


def test_audiencia_ajena_se_rechaza() -> None:
    security = pytest.importorskip("app.security")
    token, _, _ = security.issue_access_token(uuid.uuid4(), "ana")
    with pytest.raises(security.TokenError) as exc:
        security.decode_token(token, "otra-api")
    assert exc.value.code == "TOKEN_INVALID"


def test_token_vencido_se_detecta() -> None:
    security = pytest.importorskip("app.security")
    import jwt as pyjwt

    ahora = datetime.now(timezone.utc)
    payload = {
        "iss": "auth-service",
        "sub": str(uuid.uuid4()),
        "aud": ["auth-api"],
        "iat": int((ahora - timedelta(hours=2)).timestamp()),
        "exp": int((ahora - timedelta(hours=1)).timestamp()),
        "jti": str(uuid.uuid4()),
        "token_use": "access",
    }
    token = pyjwt.encode(payload, security._private_key(), algorithm="RS256",
                         headers={"kid": security.get_settings().auth_jwt_kid})
    with pytest.raises(security.TokenError) as exc:
        security.decode_token(token, "auth-api")
    assert exc.value.code == "TOKEN_EXPIRED"


def test_alg_none_se_rechaza() -> None:
    security = pytest.importorskip("app.security")
    import jwt as pyjwt

    token = pyjwt.encode({"iss": "auth-service", "sub": str(uuid.uuid4())}, None, algorithm="none")
    with pytest.raises(security.TokenError) as exc:
        security.decode_token(token, "auth-api")
    assert exc.value.code == "TOKEN_INVALID"


def test_jwks_solo_expone_material_publico() -> None:
    security = pytest.importorskip("app.security")
    jwks = security.public_jwks()
    assert len(jwks["keys"]) == 1
    key = jwks["keys"][0]
    assert key["kty"] == "RSA" and key["alg"] == "RS256" and key["use"] == "sig"
    assert key["kid"]
    for privado in ("d", "p", "q", "dp", "dq", "qi"):
        assert privado not in key


# ----------------------------------------------------------------- STEGO


def _imagen(ruido: int = 60):
    pillow = pytest.importorskip("PIL.Image")
    return pillow.effect_noise((256, 256), ruido).convert("RGB")


def _con_carga(image):
    rng = __import__("random").Random(7)
    copia = image.copy()
    pixels = copia.load()
    for y in range(copia.height):
        for x in range(copia.width):
            r, g, b = pixels[x, y]
            pixels[x, y] = (r, g, (b & 0xFE) | rng.randrange(2))
    return copia


def _analizar(image):
    lsb = pytest.importorskip("app.lsb")
    return lsb.analyze_image(
        image,
        threshold=0.75,
        min_pixels=16384,
        min_palette_colors=16,
    )


def test_chi_cuadrado_conoce_sus_valores() -> None:
    lsb = pytest.importorskip("app.lsb")
    # Grados de libertad altos: la supervivencia cae rápido al alejarse del centro.
    assert lsb.chi_square_survival(0.0) == pytest.approx(1.0, abs=1e-6)
    assert 0.0 <= lsb.chi_square_survival(500.0) <= 1.0
    assert lsb.chi_square_survival(500.0) < lsb.chi_square_survival(10.0)


def test_detector_separa_limpia_de_cargada() -> None:
    limpia = _analizar(_imagen())
    cargada = _analizar(_con_carga(_imagen()))
    assert limpia.status in {"sin_indicios", "no_concluyentes"}
    assert cargada.indicators["anomaly_score"] > limpia.indicators["anomaly_score"]
    assert cargada.status in {"sospechosos", "no_concluyentes"}


def test_limitations_nunca_esta_vacia() -> None:
    for imagen in (_imagen(), _con_carga(_imagen())):
        resultado = _analizar(imagen)
        assert resultado.limitations.strip()


def test_imagen_diminuta_es_no_concluyente() -> None:
    lsb = pytest.importorskip("app.lsb")
    diminuta = _imagen().resize((16, 16))
    resultado = lsb.analyze_image(diminuta, threshold=0.75, min_pixels=16384, min_palette_colors=16)
    assert resultado.status == "no_concluyentes"
    assert resultado.action == "advertencia"
