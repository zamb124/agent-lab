from __future__ import annotations

import secrets
from datetime import UTC, datetime
from urllib.parse import quote

from core.config import get_settings
from core.short_links.kinds import (
    SHORT_LINK_KIND_COMPANY_INVITE,
    SHORT_LINK_KIND_FLOW_PREVIEW_EMBED,
    SHORT_LINK_KIND_SYNC_CALL_JOIN,
)
from core.short_links.payloads import CompanyInvitePayload, SyncCallJoinPayload
from core.short_links.repository import ShortLinkRepository


def _random_code() -> str:
    raw = secrets.token_urlsafe(12).replace("=", "")
    if len(raw) < 12:
        raw = secrets.token_urlsafe(16).replace("=", "")
    return raw[:16]


def require_platform_public_base_url() -> str:
    settings = get_settings()
    base = settings.server.platform_public_base_url
    if base is None or str(base).strip() == "":
        raise ValueError("server.platform_public_base_url не задан: нужен для коротких ссылок")
    return str(base).strip().rstrip("/")


class ShortLinkService:
    def __init__(
        self,
        db_url: str | None = None,
        repository: ShortLinkRepository | None = None,
    ) -> None:
        self._repo = repository if repository is not None else ShortLinkRepository(db_url=db_url)

    def public_short_url(self, code: str) -> str:
        base = require_platform_public_base_url()
        return f"{base}/l/{code}"

    async def mint_sync_call_join(
        self, link_token: str, expires_at: datetime, company_id: str
    ) -> str:
        payload_model = SyncCallJoinPayload(link_token=link_token, company_id=company_id)
        payload = payload_model.model_dump()

        existing_any = await self._repo.find_sync_by_link_token(link_token)
        if existing_any is not None:
            await self._repo.update_expires_at(existing_any.code, expires_at)
            return self.public_short_url(existing_any.code)

        for _ in range(12):
            code = _random_code()
            ok = await self._repo.insert_try(
                code,
                SHORT_LINK_KIND_SYNC_CALL_JOIN,
                payload,
                expires_at,
            )
            if ok:
                return self.public_short_url(code)

        raise RuntimeError("Не удалось выделить уникальный код короткой ссылки")

    async def mint_company_invite(self, jwt: str, expires_at: datetime) -> str:
        payload_model = CompanyInvitePayload(jwt=jwt)
        payload = payload_model.model_dump()

        for _ in range(12):
            code = _random_code()
            ok = await self._repo.insert_try(
                code,
                SHORT_LINK_KIND_COMPANY_INVITE,
                payload,
                expires_at,
            )
            if ok:
                return self.public_short_url(code)

        raise RuntimeError("Не удалось выделить уникальный код короткой ссылки")

    async def mint_flow_preview_embed(self, handoff_id: str, expires_at: datetime) -> str:
        if not isinstance(handoff_id, str) or not handoff_id.strip():
            raise ValueError("handoff_id must be non-empty string")
        payload = {"handoff_id": handoff_id.strip()}

        for _ in range(12):
            code = _random_code()
            ok = await self._repo.insert_try(
                code,
                SHORT_LINK_KIND_FLOW_PREVIEW_EMBED,
                payload,
                expires_at,
            )
            if ok:
                return self.public_short_url(code)

        raise RuntimeError("Не удалось выделить уникальный код короткой ссылки")

    async def resolve_absolute_redirect_url(self, code: str) -> str | None:
        row = await self._repo.get_by_code(code)
        if row is None:
            return None
        now = datetime.now(UTC)
        if row.expires_at <= now:
            return None

        if row.kind == SHORT_LINK_KIND_SYNC_CALL_JOIN:
            token = row.payload.get("link_token")
            if not isinstance(token, str) or token == "":
                return None
            base = require_platform_public_base_url()
            cid = row.payload.get("company_id")
            if isinstance(cid, str) and cid != "":
                return f"{base}/sync/join/{token}?company_id={quote(cid, safe='')}"
            return f"{base}/sync/join/{token}"

        base = require_platform_public_base_url()

        if row.kind == SHORT_LINK_KIND_COMPANY_INVITE:
            return f"{base}/join?c={quote(code, safe='')}"

        return None

    async def delete_by_code(self, code: str) -> bool:
        return await self._repo.delete_by_code(code)

    async def delete_sync_by_link_token(self, link_token: str) -> int:
        return await self._repo.delete_sync_by_link_token(link_token)

    async def get_invite_jwt_by_code(self, code: str) -> str | None:
        """JWT для accept после проверки срока и kind."""
        row = await self._repo.get_by_code(code)
        if row is None:
            return None
        now = datetime.now(UTC)
        if row.expires_at <= now:
            return None
        if row.kind != SHORT_LINK_KIND_COMPANY_INVITE:
            return None
        jwt = row.payload.get("jwt")
        if not isinstance(jwt, str) or jwt == "":
            return None
        return jwt
