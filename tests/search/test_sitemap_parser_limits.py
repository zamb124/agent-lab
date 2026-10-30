"""Лимиты обнаружения sitemap через настоящий HTTP-клиент."""

from __future__ import annotations

from collections.abc import Callable

import httpx2
import pytest

from apps.search.services.crawl.sitemap_parser import _append_entries, discover_sitemap_urls
from apps.search.crawl.url_filter import CrawlUrlFilter
from tests.core.http_proxy_helpers import install_mock_httpx_client

_PERMISSIVE_FILTER = CrawlUrlFilter(include_patterns=[], exclude_patterns=[], exclude_extensions=[])


def _site(body: bytes) -> Callable[[httpx2.Request], httpx2.Response]:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/sitemap.xml":
            return httpx2.Response(200, content=body, request=request)
        return httpx2.Response(404, request=request)

    return handler


def test_append_entries_stops_at_max_urls() -> None:
    collected: list[object] = []
    entries = [object(), object(), object()]
    limit_reached = _append_entries(collected, entries, max_urls=2)
    assert limit_reached is True
    assert len(collected) == 2


@pytest.mark.asyncio
async def test_discover_sitemap_urls_respects_max_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    url_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/a</loc></url>
  <url><loc>https://example.com/b</loc></url>
  <url><loc>https://example.com/c</loc></url>
</urlset>
"""
    install_mock_httpx_client(monkeypatch, _site(url_xml))
    entries = await discover_sitemap_urls(
        "example.com",
        timeout_seconds=5.0,
        max_urls=2,
        max_sitemap_bytes=1_048_576,
        url_filter=_PERMISSIVE_FILTER,
    )

    assert len(entries) == 2
    assert {entry.url for entry in entries} == {"https://example.com/a", "https://example.com/b"}


@pytest.mark.asyncio
async def test_discover_sitemap_urls_skips_oversized_xml(monkeypatch: pytest.MonkeyPatch) -> None:
    install_mock_httpx_client(monkeypatch, _site(b"x" * 2048))
    entries = await discover_sitemap_urls(
        "example.com",
        timeout_seconds=5.0,
        max_urls=10,
        max_sitemap_bytes=1024,
        url_filter=_PERMISSIVE_FILTER,
    )

    assert len(entries) == 1
    assert entries[0].url == "https://example.com/"


@pytest.mark.asyncio
async def test_discover_sitemap_urls_invalid_xml_falls_back_to_homepage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mock_httpx_client(monkeypatch, _site(b"<html><body>not xml</body></html>"))
    entries = await discover_sitemap_urls(
        "example.com",
        timeout_seconds=5.0,
        max_urls=10,
        max_sitemap_bytes=1_048_576,
        url_filter=_PERMISSIVE_FILTER,
    )

    assert len(entries) == 1
    assert entries[0].url == "https://example.com/"
