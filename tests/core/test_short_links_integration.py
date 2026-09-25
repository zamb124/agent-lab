"""Интеграция core.short_links с platform_shared: PostgreSQL, без моков."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from core.short_links import (
    SHORT_LINK_KIND_COMPANY_INVITE,
    CompanyInvitePayload,
    ShortLinkService,
)
from core.short_links.models import PlatformShortLink


@pytest.mark.asyncio
async def test_sync_mint_idempotent_resolve_and_delete(setup_database_before_tests) -> None:
    svc = ShortLinkService()
    link_token = uuid4().hex
    company_id = "test_company_join"
    expires_at = datetime.now(UTC) + timedelta(hours=2)

    url_a = await svc.mint_sync_call_join(link_token, expires_at, company_id)
    url_b = await svc.mint_sync_call_join(link_token, expires_at, company_id)
    assert url_a == url_b
    assert "/l/" in url_a

    code = url_a.rstrip("/").split("/l/")[-1]
    target = await svc.resolve_absolute_redirect_url(code)
    assert target is not None
    assert f"/sync/join/{link_token}" in target
    assert "company_id=" in target

    n = await PlatformShortLink.delete_sync_by_link_token(link_token)
    assert n >= 1
    assert await svc.resolve_absolute_redirect_url(code) is None


@pytest.mark.asyncio
async def test_invite_mint_resolve_jwt_roundtrip(setup_database_before_tests) -> None:
    svc = ShortLinkService()
    fake_jwt = "header.payload.sig"
    exp = datetime.now(UTC) + timedelta(hours=1)
    invite_url = await svc.mint_company_invite(fake_jwt, exp)
    code = invite_url.rstrip("/").split("/l/")[-1]

    loaded = await svc.get_invite_jwt_by_code(code)
    assert loaded == fake_jwt

    target = await svc.resolve_absolute_redirect_url(code)
    assert target is not None
    assert f"/join?c={code}" in target

    await PlatformShortLink.delete_by_id(code)
    assert await svc.get_invite_jwt_by_code(code) is None


@pytest.mark.asyncio
async def test_insert_try_duplicate_code_returns_false(setup_database_before_tests) -> None:
    code = f"d{uuid4().hex[:15]}"
    exp = datetime.now(UTC) + timedelta(minutes=5)
    ok1 = await PlatformShortLink.insert_try(
        code, SHORT_LINK_KIND_COMPANY_INVITE, CompanyInvitePayload(jwt="a"), exp
    )
    ok2 = await PlatformShortLink.insert_try(
        code, SHORT_LINK_KIND_COMPANY_INVITE, CompanyInvitePayload(jwt="b"), exp
    )
    assert ok1 is True
    assert ok2 is False
    await PlatformShortLink.delete_by_id(code)
