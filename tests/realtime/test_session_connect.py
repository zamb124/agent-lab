"""SESSION JWT открывает Centrifugo; API/embed/чужой iss/HMAC — нет."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from core.realtime.channels import SESSION_JWT_ISSUER, session_jwt_channels, session_jwt_meta
from core.utils.tokens import TokenType, get_token_service
from tests.realtime.centrifugo_ws import connect_centrifugo, connect_rejected


@pytest.mark.asyncio
async def test_centrifugo_connects_with_session_jwt(
    realtime_service: None,
    auth_token_system: str,
) -> None:
    _ = realtime_service
    async with connect_centrifugo(auth_token_system) as client:
        assert client._company_id == "system"


@pytest.mark.asyncio
async def test_centrifugo_rejects_missing_token(realtime_service: None) -> None:
    _ = realtime_service
    code = await connect_rejected(None)
    assert code == 3501


@pytest.mark.asyncio
async def test_centrifugo_rejects_api_jwt(
    realtime_service: None,
    system_user_id: str,
) -> None:
    _ = realtime_service
    token = get_token_service().create_api_token(system_user_id, company_id="system")
    code = await connect_rejected(token)
    assert code >= 3000 or code == 109


@pytest.mark.asyncio
async def test_centrifugo_rejects_embed_jwt(
    realtime_service: None,
    system_user_id: str,
) -> None:
    _ = realtime_service
    token = get_token_service().create_embed_session_token(
        user_id=system_user_id,
        company_id="system",
    )
    code = await connect_rejected(token)
    assert code >= 3000 or code == 109


@pytest.mark.asyncio
async def test_centrifugo_rejects_wrong_issuer(
    realtime_service: None,
    system_user_id: str,
) -> None:
    _ = realtime_service
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "user_id": system_user_id,
            "company_id": "system",
            "token_type": TokenType.SESSION.value,
            "iss": "evil.issuer",
            "channels": session_jwt_channels(system_user_id, "system"),
            "meta": session_jwt_meta("system"),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        },
        get_token_service().secret_key,
        algorithm="HS256",
    )
    code = await connect_rejected(token)
    assert code >= 3000 or code == 109


@pytest.mark.asyncio
async def test_centrifugo_rejects_wrong_hmac(
    realtime_service: None,
    system_user_id: str,
) -> None:
    _ = realtime_service
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "user_id": system_user_id,
            "company_id": "system",
            "token_type": TokenType.SESSION.value,
            "iss": SESSION_JWT_ISSUER,
            "channels": session_jwt_channels(system_user_id, "system"),
            "meta": session_jwt_meta("system"),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        },
        "wrong-hmac-secret-key-32bytes-min!!",
        algorithm="HS256",
    )
    code = await connect_rejected(token)
    assert code >= 3000 or code == 109


@pytest.mark.asyncio
async def test_centrifugo_rejects_expired_session_jwt(
    realtime_service: None,
    system_user_id: str,
) -> None:
    _ = realtime_service
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "user_id": system_user_id,
            "company_id": "system",
            "token_type": TokenType.SESSION.value,
            "iss": SESSION_JWT_ISSUER,
            "channels": session_jwt_channels(system_user_id, "system"),
            "meta": session_jwt_meta("system"),
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "exp": int((now - timedelta(hours=1)).timestamp()),
        },
        get_token_service().secret_key,
        algorithm="HS256",
    )
    code = await connect_rejected(token)
    assert code >= 3000 or code == 109
