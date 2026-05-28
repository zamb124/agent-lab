"""Юнит-тесты Sign in with Apple: client secret JWT."""

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from core.identity.providers.apple import build_apple_client_secret


@pytest.fixture
def es256_pem_keypair() -> tuple[str, str]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pub_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return priv_pem, pub_pem


def test_build_apple_client_secret_jwt_claims_and_signature(es256_pem_keypair: tuple[str, str]) -> None:
    priv_pem, pub_pem = es256_pem_keypair
    token = build_apple_client_secret(
        team_id="TEAM42",
        client_id="app.example.service",
        key_id="KEY99",
        private_key_pem=priv_pem,
        ttl_seconds=600,
    )
    headers = jwt.get_unverified_header(token)
    assert headers["alg"] == "ES256"
    assert headers["kid"] == "KEY99"

    decoded = jwt.decode(
        token,
        pub_pem,
        algorithms=["ES256"],
        audience="https://appleid.apple.com",
    )
    assert decoded["iss"] == "TEAM42"
    assert decoded["sub"] == "app.example.service"
    assert decoded["aud"] == "https://appleid.apple.com"
    assert "iat" in decoded and "exp" in decoded
    iat = decoded["iat"]
    exp = decoded["exp"]
    assert isinstance(iat, int) and isinstance(exp, int)
    assert exp - iat == 600
