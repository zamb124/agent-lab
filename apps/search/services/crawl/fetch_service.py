"""Fetch page content as markdown."""

from __future__ import annotations

import asyncio
import hashlib
import re
from typing import Literal

import trafilatura
from bs4 import BeautifulSoup

from apps.browser.contracts.crawl_fetch_types import BrowserCrawlFetchResponse
from apps.search.db.crawl_repositories import canonicalize_url
from core.clients.browser_fetch_client import BrowserFetchClient
from core.crawl.errors import CrawlExtractTooShortError
from core.crawl.models import CrawlFetchResult, CrawlStructuralSignals
from core.crawl.structural_signals import extract_structural_signals_from_html
from core.http import get_httpx_client
from core.http.text_encoding import decode_response_body_bytes

CrawlFetchTransport = Literal["http", "browser"]


class CrawlFetchService:
    def __init__(
        self,
        *,
        browser_fetch_client: BrowserFetchClient,
        browser_fetch_timeout_seconds: float,
    ) -> None:
        self._browser_fetch_client: BrowserFetchClient = browser_fetch_client
        self._browser_fetch_timeout_seconds: float = browser_fetch_timeout_seconds

    async def fetch_markdown(
        self,
        url: str,
        *,
        timeout_seconds: float,
        min_extract_chars: int,
        browser_fallback_enabled: bool,
    ) -> CrawlFetchResult:
        try:
            return await _fetch_http_markdown(
                url,
                timeout_seconds=timeout_seconds,
                min_extract_chars=min_extract_chars,
            )
        except Exception as http_error:
            if not browser_fallback_enabled:
                raise http_error from http_error
            browser_response = await self._browser_fetch_client.fetch_html(
                url,
                timeout_ms=int(timeout_seconds * 1000),
                service_timeout_seconds=self._browser_fetch_timeout_seconds,
            )
            return _build_crawl_fetch_result_from_html(
                browser_response,
                min_extract_chars=min_extract_chars,
            )


async def _fetch_http_markdown(
    url: str,
    *,
    timeout_seconds: float,
    min_extract_chars: int,
) -> CrawlFetchResult:
    async with get_httpx_client(timeout=timeout_seconds, follow_redirects=True) as client:
        response = await client.get(url)
        _ = response.raise_for_status()
        final_url = str(response.url)
        try:
            content_type = response.headers["content-type"]
        except KeyError:
            content_type = "text/html"
        markdown, structural_signals = await asyncio.to_thread(
            _extract_markdown_and_signals,
            response.content,
            content_type,
            final_url,
        )
    return _build_crawl_fetch_result(
        final_url=final_url,
        markdown=markdown,
        structural_signals=structural_signals,
        min_extract_chars=min_extract_chars,
        fetch_transport="http",
    )


def _build_crawl_fetch_result_from_html(
    browser_response: BrowserCrawlFetchResponse,
    *,
    min_extract_chars: int,
) -> CrawlFetchResult:
    html = browser_response.html
    markdown, structural_signals = _extract_markdown_and_signals(
        html.encode("utf-8"),
        "text/html",
        browser_response.final_url,
    )
    return _build_crawl_fetch_result(
        final_url=browser_response.final_url,
        markdown=markdown,
        structural_signals=structural_signals,
        min_extract_chars=min_extract_chars,
        fetch_transport="browser",
    )


def _build_crawl_fetch_result(
    *,
    final_url: str,
    markdown: str,
    structural_signals: CrawlStructuralSignals,
    min_extract_chars: int,
    fetch_transport: CrawlFetchTransport,
) -> CrawlFetchResult:
    if len(markdown.strip()) < min_extract_chars:
        raise CrawlExtractTooShortError(final_url)
    canonical_url = canonicalize_url(final_url)
    title = _resolve_title(markdown, structural_signals)
    heading_trail = _extract_heading_trail(markdown)
    content_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    return CrawlFetchResult(
        url=final_url,
        canonical_url=canonical_url,
        markdown=markdown,
        title=title,
        heading_trail=heading_trail,
        content_hash=content_hash,
        fetch_transport=fetch_transport,
        structural_signals=structural_signals,
    )


def _resolve_title(markdown: str, structural_signals: CrawlStructuralSignals) -> str:
    if structural_signals.title is not None and structural_signals.title.strip():
        return structural_signals.title.strip()
    return _extract_title(markdown)


def _extract_markdown_and_signals(
    content: bytes,
    content_type: str,
    page_url: str,
) -> tuple[str, CrawlStructuralSignals]:
    text = decode_response_body_bytes(content, content_type=content_type)
    if "html" not in content_type.lower():
        if not text.strip():
            raise ValueError("empty response body")
        return text, CrawlStructuralSignals()
    html = text
    structural_signals = extract_structural_signals_from_html(html, page_url=page_url)
    extracted = trafilatura.extract(
        html,
        output_format="markdown",
        include_links=True,
        include_tables=True,
        include_images=False,
        favor_recall=True,
    )
    if extracted is None or not extracted.strip():
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        extracted = soup.get_text(separator="\n", strip=True)
    if not extracted or not extracted.strip():
        raise ValueError("html page has no extractable text")
    return extracted, structural_signals


def _extract_title(markdown: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return "Untitled"


def _extract_heading_trail(markdown: str) -> list[str]:
    trail: list[str] = []
    for line in markdown.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if match is None:
            continue
        level = len(match.group(1))
        title = match.group(2).strip()
        if not title:
            continue
        while len(trail) >= level:
            _ = trail.pop()
        trail.append(title)
    return trail[-3:]
