"""Host-aware короткие ссылки для multi-brand apex."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from core.short_links import ShortLinkService
from core.short_links.models import PlatformShortLink


@pytest.mark.asyncio
async def test_mint_company_invite_respects_linnex_host(setup_database_before_tests) -> None:
    svc = ShortLinkService()
    fake_jwt = f"header.{uuid4().hex}.sig"
    exp = datetime.now(UTC) + timedelta(hours=1)

    invite_url = await svc.mint_company_invite(fake_jwt, exp, host="linnex.io")
    assert invite_url.startswith("https://linnex.io/l/")

    code = invite_url.rstrip("/").split("/l/")[-1]
    target = await svc.resolve_absolute_redirect_url(code, host="linnex.io")
    assert target is not None
    assert target.startswith("https://linnex.io/join?c=")

    await PlatformShortLink.delete_by_id(code)


@pytest.mark.asyncio
async def test_mint_sync_call_join_respects_linnex_host(setup_database_before_tests) -> None:
    svc = ShortLinkService()
    link_token = uuid4().hex
    company_id = f"test_company_{uuid4().hex[:8]}"
    expires_at = datetime.now(UTC) + timedelta(hours=2)

    url = await svc.mint_sync_call_join(link_token, expires_at, company_id, host="linnex.io")
    assert url.startswith("https://linnex.io/l/")

    code = url.rstrip("/").split("/l/")[-1]
    await PlatformShortLink.delete_sync_by_link_token(link_token)
    assert await svc.resolve_absolute_redirect_url(code) is None
