from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import AsyncIterator

import pytest

from apps.browser.api.mcp import _tool_call


class _FakePage:
    def __init__(self, url: str, html: str) -> None:
        self.url = url
        self._html = html

    async def content(self) -> str:
        return self._html


class _FakeLeaseManager:
    def __init__(self, page: _FakePage) -> None:
        self._page = page

    @asynccontextmanager
    async def session_navigate_exclusive(self, session_id: str) -> AsyncIterator[None]:
        _ = session_id
        yield

    async def get_page_for_session(self, session_id: str) -> _FakePage:
        if session_id != "sess-1":
            raise KeyError("session not found")
        return self._page


class _FakeFileProcessor:
    async def process_file_from_bytes(self, **kwargs):
        data = kwargs["data"]
        if not isinstance(data, bytes) or len(data) == 0:
            raise ValueError("expected non-empty bytes")
        return SimpleNamespace(
            file_id="file_test_1",
            s3_bucket="files",
            s3_key="files/file_test_1.html",
            storage_url=None,
            file_size=len(data),
            content_type="text/html",
        )


@pytest.mark.asyncio
async def test_tool_call_save_html_to_s3_returns_s3_path_and_links() -> None:
    html = """
    <html><body>
      <a href="/first">first</a>
      <a href="https://example.org/second">second</a>
    </body></html>
    """.strip()
    container = SimpleNamespace(
        browser_runtime=SimpleNamespace(
            lease_manager=_FakeLeaseManager(_FakePage("https://example.com/root", html))
        ),
        file_processor=_FakeFileProcessor(),
    )
    result = await _tool_call(
        tool_name="browser_save_html_to_s3",
        arguments={"session_id": "sess-1", "links_limit": 5},
        container=container,  # pyright: ignore[reportArgumentType]
    )
    assert result.isError is False
    text_raw = result.content[0].get("text")
    assert isinstance(text_raw, str)
    payload = json.loads(text_raw)
    assert payload["file_id"] == "file_test_1"
    assert payload["s3_path"] == "s3://files/files/file_test_1.html"
    assert payload["links"] == [
        "https://example.com/first",
        "https://example.org/second",
    ]
