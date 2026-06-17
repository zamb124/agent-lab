"""Unit tests for sitemap discovery limits."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.search.services.crawl.sitemap_parser import _append_entries, discover_sitemap_urls


def test_append_entries_stops_at_max_urls() -> None:
    collected: list[object] = []
    entries = [object(), object(), object()]
    limit_reached = _append_entries(collected, entries, max_urls=2)
    assert limit_reached is True
    assert len(collected) == 2


@pytest.mark.asyncio
async def test_discover_sitemap_urls_respects_max_urls() -> None:
    url_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/a</loc></url>
  <url><loc>https://example.com/b</loc></url>
  <url><loc>https://example.com/c</loc></url>
</urlset>
"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = url_xml
    mock_response.text = ""

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "apps.search.services.crawl.sitemap_parser.get_httpx_client",
        return_value=mock_cm,
    ):
        entries = await discover_sitemap_urls(
            "example.com",
            timeout_seconds=5.0,
            max_urls=2,
            max_sitemap_bytes=1_048_576,
        )

    assert len(entries) == 2
    urls = {entry.url for entry in entries}
    assert urls == {"https://example.com/a", "https://example.com/b"}


@pytest.mark.asyncio
async def test_discover_sitemap_urls_skips_oversized_xml() -> None:
    huge = b"x" * 2048
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = huge
    mock_response.text = ""

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "apps.search.services.crawl.sitemap_parser.get_httpx_client",
        return_value=mock_cm,
    ):
        entries = await discover_sitemap_urls(
            "example.com",
            timeout_seconds=5.0,
            max_urls=10,
            max_sitemap_bytes=1024,
        )

    assert len(entries) == 1
    assert entries[0].url == "https://example.com/"


@pytest.mark.asyncio
async def test_discover_sitemap_urls_invalid_xml_falls_back_to_homepage() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"<html><body>not xml</body></html>"
    mock_response.text = ""

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "apps.search.services.crawl.sitemap_parser.get_httpx_client",
        return_value=mock_cm,
    ):
        entries = await discover_sitemap_urls(
            "example.com",
            timeout_seconds=5.0,
            max_urls=10,
            max_sitemap_bytes=1_048_576,
        )

    assert len(entries) == 1
    assert entries[0].url == "https://example.com/"
