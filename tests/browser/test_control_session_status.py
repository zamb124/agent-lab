"""Control API: status закрытой browser-сессии."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.browser.api import control
from core.authz.models import AuthzObject
from core.clients.browser.control_types import ControlSessionStatusResponse


class _StubAuthz:
    async def require_can_view(self, obj: AuthzObject) -> None:
        _ = obj


class _ClosedSessionLeaseManager:
    async def get_page_for_session(self, session_id: str) -> object:
        raise KeyError(f"Нет активной страницы для session_id={session_id}")

    async def is_session_recently_closed(self, session_id: str) -> bool:
        return session_id == "sess-closed"


class _UnknownSessionLeaseManager:
    async def get_page_for_session(self, session_id: str) -> object:
        raise KeyError(f"Нет активной страницы для session_id={session_id}")

    async def is_session_recently_closed(self, _session_id: str) -> bool:
        return False


@pytest.mark.asyncio
async def test_control_session_status_returns_closed_for_recently_closed_session() -> None:
    di = SimpleNamespace(
        authz_service=_StubAuthz(),
        browser_runtime=SimpleNamespace(
            lease_manager=_ClosedSessionLeaseManager(),
        ),
    )
    status = await control.control_session_status("sess-closed", di)  # pyright: ignore[reportArgumentType]
    assert isinstance(status, ControlSessionStatusResponse)
    assert status.session_id == "sess-closed"
    assert status.closed is True
    assert status.url == ""
    assert status.title == ""
    assert status.human_takeover is False


@pytest.mark.asyncio
async def test_control_session_status_unknown_session_returns_404() -> None:
    di = SimpleNamespace(
        authz_service=_StubAuthz(),
        browser_runtime=SimpleNamespace(
            lease_manager=_UnknownSessionLeaseManager(),
        ),
    )
    with pytest.raises(HTTPException) as exc_info:
        _ = await control.control_session_status("sess-unknown", di)  # pyright: ignore[reportArgumentType]
    assert exc_info.value.status_code == 404
