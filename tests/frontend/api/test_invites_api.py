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
from urllib.parse import urlparse

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from core.config import get_settings
from core.models.identity_models import Company, User
from core.utils.invite_tokens import (
    INVITE_REDIS_KEY_PREFIX,
    INVITE_TOKEN_AUDIENCE,
    INVITE_TOKEN_TYPE,
    get_invite_token_service,
)
from core.short_links.kinds import SHORT_LINK_KIND_COMPANY_INVITE
from core.short_links.repository import ShortLinkRepository
from core.utils.tokens import get_token_service


def _short_code_from_invite_url(invite_url: str) -> str:
    parsed = urlparse(invite_url)
    path = parsed.path or ""
    if not path.startswith("/l/"):
        raise ValueError(f"Ожидался путь /l/{{code}} в invite_url: {invite_url}")
    segments = [s for s in path.split("/") if s]
    if len(segments) < 2 or segments[0] != "l":
        raise ValueError(f"Некорректный путь короткой ссылки: {path}")
    return segments[1]


async def _jwt_from_invite_url(frontend_container, invite_url: str) -> str:
    code = _short_code_from_invite_url(invite_url)
    raw = await frontend_container.short_link_service.get_invite_jwt_by_code(code)
    if raw is None:
        raise ValueError("JWT не найден по короткому коду")
    return raw


async def _insert_invite_short_link_row(jwt_str: str, expires_at: datetime) -> str:
    """Строка в platform_short_links для произвольного JWT (интеграционные ветки ошибок)."""
    settings = get_settings()
    url = settings.database.shared_url
    if not url:
        raise RuntimeError("database.shared_url не задан")
    repo = ShortLinkRepository(db_url=url)
    code = f"i{uuid.uuid4().hex[:15]}"
    ok = await repo.insert_try(
        code,
        SHORT_LINK_KIND_COMPANY_INVITE,
        {"jwt": jwt_str},
        expires_at,
    )
    if not ok:
        raise RuntimeError("Не удалось вставить тестовую короткую ссылку инвайта")
    return code


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


async def _redis_set(key: str, value: str, ex: int) -> None:
    import redis.asyncio as aioredis

    settings = get_settings()
    client = aioredis.from_url(
        settings.database.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    try:
        await client.set(key, value, ex=ex)
    finally:
        await client.aclose()


def _build_expired_invite_jwt(company_id: str, role: str, jti: str, invited_by: str) -> str:
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
        "invited_by": invited_by,
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
        "invited_by": "user_inviter_placeholder",
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
        self,
        frontend_client: AsyncClient,
        auth_headers: dict[str, str],
        auth_token: str,
        frontend_container,
    ):
        token_service = get_token_service()
        owner_data = token_service.validate_token(auth_token)
        assert owner_data is not None

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
        invite_url = data["invite_url"]
        assert "/l/" in invite_url
        jwt_str = await _jwt_from_invite_url(frontend_container, invite_url)
        assert len(jwt_str) > 20
        decoded = jwt.decode(
            jwt_str,
            get_settings().auth.jwt_secret_key,
            algorithms=["HS256"],
            audience=INVITE_TOKEN_AUDIENCE,
        )
        assert decoded.get("invited_by") == owner_data.user_id

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
        short_code = _short_code_from_invite_url(invite_url)
        invite_jwt = await _jwt_from_invite_url(frontend_container, invite_url)
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
            json={"short_code": short_code},
        )
        assert accept.status_code == 200, accept.text
        body = accept.json()
        assert body["company_id"] == target_company_id
        assert body["already_member"] is False
        assert "developer" in body["role"]
        target_company = await frontend_container.company_repository.get(target_company_id)
        assert target_company is not None
        assert body["subdomain"] == target_company.subdomain

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

        members_resp = await frontend_client.get(
            "/frontend/api/team/members",
            headers=auth_headers,
        )
        assert members_resp.status_code == 200, members_resp.text
        members = members_resp.json()["items"]
        member_ids = {m["user_id"] for m in members}
        assert owner_data.user_id in member_ids
        assert invitee_id.user_id in member_ids
        assert len(members) >= 2

    async def test_accept_second_user_same_short_code_returns_404(
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
        invite_url = gen.json()["invite_url"]
        short_code = _short_code_from_invite_url(invite_url)

        _, h1 = await _create_invitee_no_company(frontend_container)
        _, h2 = await _create_invitee_no_company(frontend_container)

        r1 = await frontend_client.post(
            "/frontend/api/invites/accept",
            headers=h1,
            json={"short_code": short_code},
        )
        assert r1.status_code == 200
        b1 = r1.json()
        co = await frontend_container.company_repository.get(b1["company_id"])
        assert co is not None
        assert b1["subdomain"] == co.subdomain

        r2 = await frontend_client.post(
            "/frontend/api/invites/accept",
            headers=h2,
            json={"short_code": short_code},
        )
        assert r2.status_code == 404

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
        invite_url = gen.json()["invite_url"]
        short_code = _short_code_from_invite_url(invite_url)
        invite_jwt = await _jwt_from_invite_url(frontend_container, invite_url)
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
            json={"short_code": short_code},
        )
        assert accept.status_code == 200
        owner_co = await frontend_container.company_repository.get(owner_data.company_id)
        assert owner_co is not None
        body_accept = accept.json()
        assert body_accept["already_member"] is True
        assert body_accept["subdomain"] == owner_co.subdomain
        set_cookie_vals = [v for k, v in accept.headers.multi_items() if k.lower() == "set-cookie"]
        assert any(v.startswith("auth_token=") for v in set_cookie_vals)

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
        expired = _build_expired_invite_jwt(cid, "developer", jti, owner_data.user_id)
        row_expires = datetime.now(timezone.utc) + timedelta(hours=24)
        short_code = await _insert_invite_short_link_row(expired, row_expires)

        _, invitee_headers = await _create_invitee_no_company(frontend_container)

        response = await frontend_client.post(
            "/frontend/api/invites/accept",
            headers=invitee_headers,
            json={"short_code": short_code},
        )
        assert response.status_code == 410

    async def test_accept_invalid_signature_403(
        self, frontend_client: AsyncClient, auth_token: str, frontend_container
    ):
        token_service = get_token_service()
        owner_data = token_service.validate_token(auth_token)
        assert owner_data is not None

        bad = _build_wrong_signature_invite_jwt(owner_data.company_id)
        row_expires = datetime.now(timezone.utc) + timedelta(hours=24)
        short_code = await _insert_invite_short_link_row(bad, row_expires)
        _, invitee_headers = await _create_invitee_no_company(frontend_container)

        response = await frontend_client.post(
            "/frontend/api/invites/accept",
            headers=invitee_headers,
            json={"short_code": short_code},
        )
        assert response.status_code == 403

    async def test_accept_company_missing_404(
        self,
        frontend_client: AsyncClient,
        auth_token: str,
        frontend_container,
    ):
        missing_id = f"missing_co_{uuid.uuid4().hex[:16]}"
        jti = f"jti_miss_{uuid.uuid4().hex[:12]}"
        settings = get_settings()
        now = datetime.now(timezone.utc)
        token_service = get_token_service()
        owner_data = token_service.validate_token(auth_token)
        assert owner_data is not None
        payload: dict[str, Any] = {
            "typ": INVITE_TOKEN_TYPE,
            "aud": INVITE_TOKEN_AUDIENCE,
            "company_id": missing_id,
            "role": "developer",
            "invited_by": owner_data.user_id,
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        }
        invite_jwt = jwt.encode(payload, settings.auth.jwt_secret_key, algorithm="HS256")
        row_expires = datetime.now(timezone.utc) + timedelta(hours=24)
        short_code = await _insert_invite_short_link_row(invite_jwt, row_expires)

        _, invitee_headers = await _create_invitee_no_company(frontend_container)

        response = await frontend_client.post(
            "/frontend/api/invites/accept",
            headers=invitee_headers,
            json={"short_code": short_code},
        )
        assert response.status_code == 404

    async def test_accept_unauthorized(self, frontend_client: AsyncClient):
        response = await frontend_client.post(
            "/frontend/api/invites/accept",
            json={"short_code": "any"},
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
        invite_url = gen.json()["invite_url"]
        short_code = _short_code_from_invite_url(invite_url)

        foreign_loaded = await frontend_container.company_repository.get(foreign_id)
        assert foreign_loaded is not None
        _, invitee_headers = await _create_invitee_other_company(
            frontend_container, foreign_loaded
        )

        accept = await frontend_client.post(
            "/frontend/api/invites/accept",
            headers=invitee_headers,
            json={"short_code": short_code},
        )
        assert accept.status_code == 200
        body = accept.json()
        assert body["company_id"] == target_id
        assert "viewer" in body["role"]
        target_co = await frontend_container.company_repository.get(target_id)
        assert target_co is not None
        assert body["subdomain"] == target_co.subdomain

        uid = token_service.validate_token(
            invitee_headers["Authorization"].replace("Bearer ", "")
        )
        assert uid is not None
        user = await frontend_container.user_repository.get(uid.user_id)
        assert user is not None
        assert target_id in user.companies
        assert foreign_loaded.company_id in user.companies


@pytest.mark.asyncio
class TestInvitesPreviewAPI:
    async def test_preview_success_without_auth(
        self,
        frontend_client: AsyncClient,
        auth_headers: dict[str, str],
        auth_token: str,
        frontend_container,
    ):
        token_service = get_token_service()
        owner_data = token_service.validate_token(auth_token)
        assert owner_data is not None
        owner_user = await frontend_container.user_repository.get(owner_data.user_id)
        assert owner_user is not None

        gen = await frontend_client.post(
            "/frontend/api/invites/generate",
            headers=auth_headers,
            json={"role": "developer"},
        )
        assert gen.status_code == 200
        invite_url = gen.json()["invite_url"]
        short_code = _short_code_from_invite_url(invite_url)

        preview = await frontend_client.post(
            "/frontend/api/invites/preview",
            json={"short_code": short_code},
        )
        assert preview.status_code == 200
        body = preview.json()
        assert body["company_id"] == owner_data.company_id
        assert body["role"] == "developer"
        assert body["invited_by_user_id"] == owner_data.user_id
        assert body["invited_by_name"] == owner_user.name
        assert len(body["company_name"]) > 0

    async def test_preview_unknown_short_code_404(self, frontend_client: AsyncClient):
        response = await frontend_client.post(
            "/frontend/api/invites/preview",
            json={"short_code": f"unknown_{uuid.uuid4().hex}"},
        )
        assert response.status_code == 404

    async def test_preview_expired_token_410(
        self,
        frontend_client: AsyncClient,
        auth_token: str,
        frontend_container,
    ):
        token_service = get_token_service()
        owner_data = token_service.validate_token(auth_token)
        assert owner_data is not None
        cid = owner_data.company_id
        jti = f"exp_prev_{uuid.uuid4().hex[:12]}"
        expired = _build_expired_invite_jwt(cid, "developer", jti, owner_data.user_id)
        row_expires = datetime.now(timezone.utc) + timedelta(hours=24)
        short_code = await _insert_invite_short_link_row(expired, row_expires)

        response = await frontend_client.post(
            "/frontend/api/invites/preview",
            json={"short_code": short_code},
        )
        assert response.status_code == 410

    async def test_preview_inviter_missing_404(
        self,
        frontend_client: AsyncClient,
        auth_token: str,
        frontend_container,
    ):
        token_service = get_token_service()
        owner_data = token_service.validate_token(auth_token)
        assert owner_data is not None
        cid = owner_data.company_id
        fake_inviter = f"no_such_user_{uuid.uuid4().hex[:12]}"
        jti = f"jti_prev_{uuid.uuid4().hex[:12]}"
        settings = get_settings()
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "typ": INVITE_TOKEN_TYPE,
            "aud": INVITE_TOKEN_AUDIENCE,
            "company_id": cid,
            "role": "developer",
            "invited_by": fake_inviter,
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        }
        raw = jwt.encode(payload, settings.auth.jwt_secret_key, algorithm="HS256")
        row_expires = datetime.now(timezone.utc) + timedelta(hours=24)
        short_code = await _insert_invite_short_link_row(raw, row_expires)

        response = await frontend_client.post(
            "/frontend/api/invites/preview",
            json={"short_code": short_code},
        )
        assert response.status_code == 404

    async def test_preview_jti_already_used_410(
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
        invite_url = gen.json()["invite_url"]
        short_code = _short_code_from_invite_url(invite_url)
        jwt_str = await _jwt_from_invite_url(frontend_container, invite_url)
        invite_data = get_invite_token_service().validate(jwt_str)
        await _redis_set(
            f"{INVITE_REDIS_KEY_PREFIX}{invite_data.jti}",
            "1",
            ex=86400,
        )

        response = await frontend_client.post(
            "/frontend/api/invites/preview",
            json={"short_code": short_code},
        )
        assert response.status_code == 410


class TestShortLinkResolveInviteAPI:
    @pytest.mark.asyncio
    async def test_get_l_redirects_to_join_with_same_code(
        self, frontend_client: AsyncClient, auth_headers: dict[str, str]
    ):
        from apps.frontend.main import app as frontend_asgi_app

        gen = await frontend_client.post(
            "/frontend/api/invites/generate",
            headers=auth_headers,
            json={"role": "developer"},
        )
        assert gen.status_code == 200
        invite_url = gen.json()["invite_url"]
        code = _short_code_from_invite_url(invite_url)
        transport = ASGITransport(app=frontend_asgi_app)
        async with AsyncClient(transport=transport, base_url="http://testserver", follow_redirects=False) as raw:
            r = await raw.get(f"/l/{code}")
        assert r.status_code == 303
        loc = r.headers.get("location")
        assert loc is not None
        assert loc.endswith(f"/join?c={code}")

    @pytest.mark.asyncio
    async def test_get_l_unknown_code_404(self) -> None:
        from apps.frontend.main import app as frontend_asgi_app

        transport = ASGITransport(app=frontend_asgi_app)
        async with AsyncClient(transport=transport, base_url="http://testserver", follow_redirects=False) as raw:
            r = await raw.get("/l/zzzzzzzzzzzzzzzz")
        assert r.status_code == 404


class TestInviteTokenServiceUnit:
    """Прямая проверка сервиса токенов (тот же код, что и в API)."""

    def test_create_validate_roundtrip(self):
        from core.utils.invite_tokens import get_invite_token_service

        svc = get_invite_token_service()
        cid = f"co_{uuid.uuid4().hex[:8]}"
        inviter = f"user_{uuid.uuid4().hex[:10]}"
        jwt_str, jti = svc.create(cid, "admin", invited_by=inviter)
        data = svc.validate(jwt_str)
        assert data.company_id == cid
        assert data.role == "admin"
        assert data.invited_by == inviter
        assert data.jti == jti
