from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast

import pytest

from apps.browser.api.mcp import _tool_call  # pyright: ignore[reportPrivateUsage]
from core.files.object_storage import PLATFORM_STORAGE_ID


class _FakePage:
    url: str
    _html: str

    def __init__(self, url: str, html: str) -> None:
        self.url = url
        self._html = html

    async def content(self) -> str:
        return self._html


class _FakeLeaseManager:
    _page: _FakePage

    def __init__(self, page: _FakePage) -> None:
        self._page = page

    async def human_takeover_for_session(self, session_id: str) -> None:
        _ = session_id
        return None

    @asynccontextmanager
    async def session_navigate_exclusive(self, session_id: str) -> AsyncGenerator[None]:
        _ = session_id
        yield

    async def get_page_for_session(self, session_id: str) -> _FakePage:
        if session_id != "sess-1":
            raise KeyError("session not found")
        return self._page


class _FakeFilesService:
    async def create(self, **kwargs: object) -> SimpleNamespace:
        data = kwargs["data"]
        if not isinstance(data, bytes) or len(data) == 0:
            raise ValueError("expected non-empty bytes")
        return SimpleNamespace(
            file_id="file_test_1",
            storage_id=PLATFORM_STORAGE_ID,
            s3_key="files/file_test_1.html",
            storage_url=None,
            file_size=len(data),
            content_type=kwargs.get("content_type", "text/html"),
        )


@pytest.mark.asyncio
async def test_tool_call_save_html_to_s3_returns_s3_path_and_links() -> None:
    html = """
    <html><body>
      <a href="/first">first</a>
      <a href="https://example.org/second">second</a>
    </body></html>
    """.strip()
    di = SimpleNamespace(
        browser_runtime=SimpleNamespace(
            lease_manager=_FakeLeaseManager(_FakePage("https://example.com/root", html))
        ),
        files_service=_FakeFilesService(),
    )
    result = await _tool_call(
        tool_name="browser_save_html_to_s3",
        arguments={"session_id": "sess-1", "links_limit": 5},
        di=di,  # pyright: ignore[reportArgumentType]
    )
    assert result.is_error is False
    text_raw = result.content[0].get("text")
    assert isinstance(text_raw, str)
    payload = cast("dict[str, object]", json.loads(text_raw))
    assert payload["file_id"] == "file_test_1"
    assert payload["s3_path"] == "s3://platform/files/file_test_1.html"
    assert payload["links"] == [
        "https://example.com/first",
        "https://example.org/second",
    ]
