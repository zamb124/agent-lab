"""SESSION JWT = Centrifugo connection JWT (HMAC как у тестового Centrifugo)."""

from __future__ import annotations

import jwt

from core.realtime.channels import SESSION_JWT_ISSUER, session_jwt_channels, session_jwt_meta
from core.utils.tokens import TokenType, get_token_service
from tests.fixtures.test_database_env import TEST_HS256_JWT_SECRET


def _decode_hs256(token: str, *, issuer: str | None) -> dict[str, object]:
    if issuer is None:
        decoded = jwt.decode(
            token,
            get_token_service().secret_key,
            algorithms=["HS256"],
            options={"require": ["exp", "iat"]},
        )
    else:
        decoded = jwt.decode(
            token,
            get_token_service().secret_key,
            algorithms=["HS256"],
            options={"require": ["exp", "iat"]},
            issuer=issuer,
        )
    if not isinstance(decoded, dict):
        raise AssertionError("JWT payload must be object")
    return decoded


def test_test_stack_jwt_secret_matches_centrifugo_hmac() -> None:
    assert get_token_service().secret_key == TEST_HS256_JWT_SECRET


def test_session_jwt_has_centrifugo_claims() -> None:
    token = get_token_service().create_token("user_session_cf", company_id="acme")
    payload = _decode_hs256(token, issuer=SESSION_JWT_ISSUER)
    assert payload["iss"] == SESSION_JWT_ISSUER
    assert payload["user_id"] == "user_session_cf"
    assert payload["company_id"] == "acme"
    assert payload["channels"] == session_jwt_channels("user_session_cf", "acme")
    assert payload["meta"] == session_jwt_meta("acme")
    assert payload["token_type"] == TokenType.SESSION.value


def test_session_jwt_without_company_skips_company_channel() -> None:
    token = get_token_service().create_token("user_session_cf", company_id="")
    payload = _decode_hs256(token, issuer=SESSION_JWT_ISSUER)
    assert payload["channels"] == session_jwt_channels("user_session_cf", "")
    assert "company:" not in ",".join(payload["channels"])
    assert payload["meta"] == session_jwt_meta("")


def test_api_jwt_has_no_centrifugo_claims() -> None:
    token = get_token_service().create_api_token("user_api_cf", company_id="acme")
    payload = _decode_hs256(token, issuer=None)
    assert "iss" not in payload
    assert "channels" not in payload
    meta = payload.get("meta")
    if meta is not None and meta != {}:
        if not isinstance(meta, dict):
            raise AssertionError("API JWT meta must be object or empty")
        assert "company_id" not in meta
    assert payload["token_type"] == TokenType.API.value


def test_embed_session_jwt_has_no_centrifugo_claims() -> None:
    token = get_token_service().create_embed_session_token(
        user_id="user_embed_cf",
        company_id="acme",
    )
    payload = _decode_hs256(token, issuer=None)
    assert "iss" not in payload
    assert "channels" not in payload
    assert payload["token_type"] == TokenType.EMBED_SESSION.value
