from __future__ import annotations

import secrets
from datetime import UTC, datetime
from urllib.parse import quote

from core.config import get_settings
from core.platform_brand.resolver import resolve_public_base_url
from core.short_links.kinds import (
    SHORT_LINK_KIND_COMPANY_INVITE,
    SHORT_LINK_KIND_FLOW_PREVIEW_EMBED,
    SHORT_LINK_KIND_FLOW_UI_SESSION_SHARE,
    SHORT_LINK_KIND_SYNC_CALL_JOIN,
)
from core.short_links.payloads import (
    CompanyInvitePayload,
    FlowPreviewEmbedPayload,
    FlowUISessionSharePayload,
    SyncCallJoinPayload,
)
from core.short_links.repository import ShortLinkRepository


def _random_code() -> str:
    raw = secrets.token_urlsafe(12).replace("=", "")
    if len(raw) < 12:
        raw = secrets.token_urlsafe(16).replace("=", "")
    return raw[:16]


def require_platform_public_base_url(*, host: str | None = None) -> str:
    if host is not None and str(host).strip():
        return resolve_public_base_url(str(host).strip()).rstrip("/")
    settings = get_settings()
    base = settings.server.platform_public_base_url
    if base is None or str(base).strip() == "":
        raise ValueError('server.platform_public_base_url is not set: required for short links')
    return str(base).strip().rstrip("/")


class ShortLinkService:
    def __init__(
        self,
        repository: ShortLinkRepository,
    ) -> None:
        """``repository`` собирается контейнером (`BaseContainer.short_link_service`)."""
        self._repo: ShortLinkRepository = repository

    def public_short_url(self, code: str, *, host: str | None = None) -> str:
        base = require_platform_public_base_url(host=host)
        return f"{base}/l/{code}"

    async def mint_sync_call_join(
        self,
        link_token: str,
        expires_at: datetime,
        company_id: str,
        *,
        host: str | None = None,
    ) -> str:
        payload = SyncCallJoinPayload(link_token=link_token, company_id=company_id)

        existing_any = await self._repo.find_sync_by_link_token(link_token)
        if existing_any is not None:
            await self._repo.update_expires_at(existing_any.code, expires_at)
            return self.public_short_url(existing_any.code, host=host)

        for _ in range(12):
            code = _random_code()
            ok = await self._repo.insert_try(
                code,
                SHORT_LINK_KIND_SYNC_CALL_JOIN,
                payload,
                expires_at,
            )
            if ok:
                return self.public_short_url(code, host=host)

        raise RuntimeError('Failed to allocate a unique short-link code')

    async def mint_company_invite(
        self,
        jwt: str,
        expires_at: datetime,
        *,
        host: str | None = None,
    ) -> str:
        payload = CompanyInvitePayload(jwt=jwt)

        for _ in range(12):
            code = _random_code()
            ok = await self._repo.insert_try(
                code,
                SHORT_LINK_KIND_COMPANY_INVITE,
                payload,
                expires_at,
            )
            if ok:
                return self.public_short_url(code, host=host)

        raise RuntimeError('Failed to allocate a unique short-link code')

    async def mint_flow_preview_embed(self, handoff_id: str, expires_at: datetime) -> str:
        payload = FlowPreviewEmbedPayload(handoff_id=handoff_id)

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

        raise RuntimeError('Failed to allocate a unique short-link code')

    async def mint_flow_ui_session_share(
        self,
        grant_id: str,
        expires_at: datetime,
        *,
        host: str | None = None,
    ) -> str:
        payload = FlowUISessionSharePayload(grant_id=grant_id)
        for _ in range(12):
            code = _random_code()
            ok = await self._repo.insert_try(
                code,
                SHORT_LINK_KIND_FLOW_UI_SESSION_SHARE,
                payload,
                expires_at,
            )
            if ok:
                return self.public_short_url(code, host=host)
        raise RuntimeError('Failed to allocate a unique live-session link code')

    async def resolve_absolute_redirect_url(
        self,
        code: str,
        *,
        host: str | None = None,
    ) -> str | None:
        row = await self._repo.get_by_code(code)
        if row is None:
            return None
        now = datetime.now(UTC)
        if row.expires_at <= now:
            return None

        if row.kind == SHORT_LINK_KIND_SYNC_CALL_JOIN:
            payload = SyncCallJoinPayload.model_validate(row.payload)
            base = require_platform_public_base_url(host=host)
            company_id = quote(payload.company_id, safe="")
            return f"{base}/sync/join/{payload.link_token}?company_id={company_id}"

        base = require_platform_public_base_url(host=host)

        if row.kind == SHORT_LINK_KIND_COMPANY_INVITE:
            return f"{base}/join?c={quote(code, safe='')}"

        if row.kind == SHORT_LINK_KIND_FLOW_UI_SESSION_SHARE:
            payload = FlowUISessionSharePayload.model_validate(row.payload)
            return f"{base}/flow-session-share?grant={quote(payload.grant_id, safe='')}"

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
        payload = CompanyInvitePayload.model_validate(row.payload)
        return payload.jwt
