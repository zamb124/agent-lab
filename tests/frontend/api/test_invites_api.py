"""
Интеграционные тесты инвайтов по ссылке (JWT + Redis SET NX + API).

Без моков: реальная БД (shared), реальный Redis из DATABASE__REDIS_URL,
ASGI-клиент frontend. Единственная «синтетика» — построение просроченного JWT
тем же секретом, что и прод (проверка ветки истечения), без подмены сервисов.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from httpx import AsyncClient

from core.config import get_settings
from core.models.identity_models import Company, User
from core.utils.invite_tokens import (
    INVITE_REDIS_KEY_PREFIX,
    INVITE_TOKEN_AUDIENCE,
    INVITE_TOKEN_TYPE,
)
from core.utils.tokens import get_token_service


def _invite_token_from_url(invite_url: str) -> str:
    parsed = urlparse(invite_url)
    q = parse_qs(parsed.query)
    token = q.get("token")
    if not token or not token[0]:
        raise ValueError(f"Нет token в URL: {invite_url}")
    return token[0]


async def _redis_get(key: str) -> str | None:
    import redis.asyncio as aioredis

    settings = get_settings()
    client = aioredis.from_url(
        settings.database.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    try:
        return await client.get(key)
    finally:
        await client.aclose()


async def _redis_delete(key: str) -> None:
    import redis.asyncio as aioredis

    settings = get_settings()
    client = aioredis.from_url(
        settings.database.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    try:
        await client.delete(key)
    finally:
        await client.aclose()


def _build_expired_invite_jwt(company_id: str, role: str, jti: str) -> str:
    settings = get_settings()
    secret = settings.auth.jwt_secret_key
    if not secret:
        raise RuntimeError("auth.jwt_secret_key не задан")
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "typ": INVITE_TOKEN_TYPE,
        "aud": INVITE_TOKEN_AUDIENCE,
        "company_id": company_id,
        "role": role,
        "jti": jti,
        "iat": int((now - timedelta(days=2)).timestamp()),
        "exp": int((now - timedelta(hours=1)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _build_wrong_signature_invite_jwt(company_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "typ": INVITE_TOKEN_TYPE,
        "aud": INVITE_TOKEN_AUDIENCE,
        "company_id": company_id,
        "role": "developer",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    return jwt.encode(payload, "wrong-secret-not-platform", algorithm="HS256")


async def _create_invitee_no_company(frontend_container, name: str = "Invitee") -> tuple[str, dict[str, str]]:
    """Пользователь без компаний — как новый после OAuth до выбора компании."""
    uid = f"invitee_nc_{uuid.uuid4().hex[:10]}"
    user = User(
        user_id=uid,
        name=name,
        emails=[f"{uid}@test.local"],
        companies={},
        active_company_id="",
    )
    await frontend_container.user_repository.set(user)
    token = get_token_service().create_token(uid, company_id="", roles=[])
    return uid, {"Authorization": f"Bearer {token}"}


async def _create_invitee_other_company(
    frontend_container, foreign_company: Company
) -> tuple[str, dict[str, str]]:
    """Пользователь только в другой компании."""
    uid = f"invitee_oc_{uuid.uuid4().hex[:10]}"
    foreign_company.members[uid] = ["member"]
    await frontend_container.company_repository.set(foreign_company)

    user = User(
        user_id=uid,
        name="Other Co User",
        emails=[f"{uid}@test.local"],
        companies={foreign_company.company_id: ["member"]},
        active_company_id=foreign_company.company_id,
    )
    await frontend_container.user_repository.set(user)
    token = get_token_service().create_token(
        uid, company_id=foreign_company.company_id, roles=["member"]
    )
    return uid, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestInvitesGenerateAPI:
    async def test_generate_success_returns_url_and_role(
        self, frontend_client: AsyncClient, auth_headers: dict[str, str]
    ):
        response = await frontend_client.post(
            "/frontend/api/invites/generate",
            headers=auth_headers,
            json={"role": "developer"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "invite_url" in data
        assert data["role"] == "developer"
        assert "expires_in_seconds" in data
        assert data["expires_in_seconds"] > 0
        token = _invite_token_from_url(data["invite_url"])
        assert len(token) > 20

    async def test_generate_unauthorized(self, frontend_client: AsyncClient):
        response = await frontend_client.post(
            "/frontend/api/invites/generate",
            json={"role": "developer"},
        )
        assert response.status_code == 401

    async def test_generate_invalid_role(
        self, frontend_client: AsyncClient, auth_headers: dict[str, str]
    ):
        response = await frontend_client.post(
            "/frontend/api/invites/generate",
            headers=auth_headers,
            json={"role": "not_a_role"},
        )
        assert response.status_code == 400
        assert "роль" in response.json()["detail"].lower()

    async def test_generate_forbidden_for_viewer(
        self, frontend_client: AsyncClient, frontend_container
    ):
        company_id = f"co_viewer_{uuid.uuid4().hex[:8]}"
        viewer_id = f"user_viewer_{uuid.uuid4().hex[:8]}"
        company = Company(
            company_id=company_id,
            name="Viewer Co",
            owner_user_id="someone_else",
            members={viewer_id: ["viewer"]},
        )
        await frontend_container.company_repository.set(company)
        user = User(
            user_id=viewer_id,
            name="Viewer",
            emails=[f"{viewer_id}@t.local"],
            companies={company_id: ["viewer"]},
            active_company_id=company_id,
        )
        await frontend_container.user_repository.set(user)
        token = get_token_service().create_token(viewer_id, company_id=company_id, roles=["viewer"])
        headers = {"Authorization": f"Bearer {token}"}

        response = await frontend_client.post(
            "/frontend/api/invites/generate",
            headers=headers,
            json={"role": "developer"},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestInvitesAcceptAPI:
    async def test_accept_new_user_joins_target_company(
        self,
        frontend_client: AsyncClient,
        auth_headers: dict[str, str],
        auth_token: str,
        frontend_container,
    ):
        token_service = get_token_service()
        owner_data = token_service.validate_token(auth_token)
        assert owner_data is not None
        target_company_id = owner_data.company_id

        gen = await frontend_client.post(
            "/frontend/api/invites/generate",
            headers=auth_headers,
            json={"role": "developer"},
        )
        assert gen.status_code == 200
        invite_url = gen.json()["invite_url"]
        invite_jwt = _invite_token_from_url(invite_url)
        invite_payload = jwt.decode(
            invite_jwt,
            get_settings().auth.jwt_secret_key,
            algorithms=["HS256"],
            audience=INVITE_TOKEN_AUDIENCE,
        )
        jti = invite_payload["jti"]

        _, invitee_headers = await _create_invitee_no_company(frontend_container)

        accept = await frontend_client.post(
            "/frontend/api/invites/accept",
            headers=invitee_headers,
            json={"token": invite_jwt},
        )
        assert accept.status_code == 200, accept.text
        body = accept.json()
        assert body["company_id"] == target_company_id
        assert body["already_member"] is False
        assert "developer" in body["role"]

        invitee_id = token_service.validate_token(
            invitee_headers["Authorization"].replace("Bearer ", "")
        )
        assert invitee_id is not None
        updated = await frontend_container.user_repository.get(invitee_id.user_id)
        assert updated is not None
        assert target_company_id in updated.companies
        assert updated.active_company_id == target_company_id

        redis_val = await _redis_get(f"{INVITE_REDIS_KEY_PREFIX}{jti}")
        assert redis_val == "1"

    async def test_accept_second_user_same_link_returns_410(
        self,
        frontend_client: AsyncClient,
        auth_headers: dict[str, str],
        frontend_container,
    ):
        gen = await frontend_client.post(
            "/frontend/api/invites/generate",
            headers=auth_headers,
            json={"role": "viewer"},
        )
        assert gen.status_code == 200
        invite_jwt = _invite_token_from_url(gen.json()["invite_url"])

        _, h1 = await _create_invitee_no_company(frontend_container)
        _, h2 = await _create_invitee_no_company(frontend_container)

        r1 = await frontend_client.post(
            "/frontend/api/invites/accept",
            headers=h1,
            json={"token": invite_jwt},
        )
        assert r1.status_code == 200

        r2 = await frontend_client.post(
            "/frontend/api/invites/accept",
            headers=h2,
            json={"token": invite_jwt},
        )
        assert r2.status_code == 410
        assert "использована" in r2.json()["detail"]

    async def test_accept_already_member_idempotent_no_redis_burn(
        self,
        frontend_client: AsyncClient,
        auth_headers: dict[str, str],
        auth_token: str,
        frontend_container,
    ):
        token_service = get_token_service()
        owner_data = token_service.validate_token(auth_token)
        assert owner_data is not None

        gen = await frontend_client.post(
            "/frontend/api/invites/generate",
            headers=auth_headers,
            json={"role": "admin"},
        )
        assert gen.status_code == 200
        invite_jwt = _invite_token_from_url(gen.json()["invite_url"])
        invite_payload = jwt.decode(
            invite_jwt,
            get_settings().auth.jwt_secret_key,
            algorithms=["HS256"],
            audience=INVITE_TOKEN_AUDIENCE,
        )
        jti = invite_payload["jti"]
        key = f"{INVITE_REDIS_KEY_PREFIX}{jti}"

        await _redis_delete(key)

        accept = await frontend_client.post(
            "/frontend/api/invites/accept",
            headers=auth_headers,
            json={"token": invite_jwt},
        )
        assert accept.status_code == 200
        assert accept.json()["already_member"] is True

        after = await _redis_get(key)
        assert after is None

    async def test_accept_expired_token_410(
        self,
        frontend_client: AsyncClient,
        auth_headers: dict[str, str],
        auth_token: str,
        frontend_container,
    ):
        token_service = get_token_service()
        owner_data = token_service.validate_token(auth_token)
        assert owner_data is not None
        cid = owner_data.company_id
        jti = f"exp_jti_{uuid.uuid4().hex[:12]}"
        expired = _build_expired_invite_jwt(cid, "developer", jti)

        _, invitee_headers = await _create_invitee_no_company(frontend_container)

        response = await frontend_client.post(
            "/frontend/api/invites/accept",
            headers=invitee_headers,
            json={"token": expired},
        )
        assert response.status_code == 410

    async def test_accept_invalid_signature_403(
        self, frontend_client: AsyncClient, auth_token: str, frontend_container
    ):
        token_service = get_token_service()
        owner_data = token_service.validate_token(auth_token)
        assert owner_data is not None

        bad = _build_wrong_signature_invite_jwt(owner_data.company_id)
        _, invitee_headers = await _create_invitee_no_company(frontend_container)

        response = await frontend_client.post(
            "/frontend/api/invites/accept",
            headers=invitee_headers,
            json={"token": bad},
        )
        assert response.status_code == 403

    async def test_accept_company_missing_404(
        self,
        frontend_client: AsyncClient,
        auth_headers: dict[str, str],
        frontend_container,
    ):
        missing_id = f"missing_co_{uuid.uuid4().hex[:16]}"
        jti = f"jti_miss_{uuid.uuid4().hex[:12]}"
        settings = get_settings()
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "typ": INVITE_TOKEN_TYPE,
            "aud": INVITE_TOKEN_AUDIENCE,
            "company_id": missing_id,
            "role": "developer",
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        }
        invite_jwt = jwt.encode(payload, settings.auth.jwt_secret_key, algorithm="HS256")

        _, invitee_headers = await _create_invitee_no_company(frontend_container)

        response = await frontend_client.post(
            "/frontend/api/invites/accept",
            headers=invitee_headers,
            json={"token": invite_jwt},
        )
        assert response.status_code == 404

    async def test_accept_unauthorized(self, frontend_client: AsyncClient):
        response = await frontend_client.post(
            "/frontend/api/invites/accept",
            json={"token": "any"},
        )
        assert response.status_code == 401

    async def test_accept_invitee_from_other_company_still_joins(
        self,
        frontend_client: AsyncClient,
        auth_headers: dict[str, str],
        auth_token: str,
        frontend_container,
    ):
        token_service = get_token_service()
        owner_data = token_service.validate_token(auth_token)
        assert owner_data is not None
        target_id = owner_data.company_id

        foreign_id = f"foreign_{uuid.uuid4().hex[:8]}"
        foreign = Company(
            company_id=foreign_id,
            name="Foreign",
            owner_user_id="owner_foreign_placeholder",
            members={},
        )
        await frontend_container.company_repository.set(foreign)

        gen = await frontend_client.post(
            "/frontend/api/invites/generate",
            headers=auth_headers,
            json={"role": "viewer"},
        )
        assert gen.status_code == 200
        invite_jwt = _invite_token_from_url(gen.json()["invite_url"])

        foreign_loaded = await frontend_container.company_repository.get(foreign_id)
        assert foreign_loaded is not None
        _, invitee_headers = await _create_invitee_other_company(
            frontend_container, foreign_loaded
        )

        accept = await frontend_client.post(
            "/frontend/api/invites/accept",
            headers=invitee_headers,
            json={"token": invite_jwt},
        )
        assert accept.status_code == 200
        body = accept.json()
        assert body["company_id"] == target_id
        assert "viewer" in body["role"]

        uid = token_service.validate_token(
            invitee_headers["Authorization"].replace("Bearer ", "")
        )
        assert uid is not None
        user = await frontend_container.user_repository.get(uid.user_id)
        assert user is not None
        assert target_id in user.companies
        assert foreign_loaded.company_id in user.companies


class TestInviteTokenServiceUnit:
    """Прямая проверка сервиса токенов (тот же код, что и в API)."""

    def test_create_validate_roundtrip(self):
        from core.utils.invite_tokens import get_invite_token_service

        svc = get_invite_token_service()
        cid = f"co_{uuid.uuid4().hex[:8]}"
        jwt_str, jti = svc.create(cid, "admin")
        data = svc.validate(jwt_str)
        assert data.company_id == cid
        assert data.role == "admin"
        assert data.jti == jti
