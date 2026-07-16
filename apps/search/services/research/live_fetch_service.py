"""LiveFetchService: parallel live gather for research mode (§4.5).

Wraps CrawlFetchService for HTTP + browser fetch; never writes to RAG.
All markdown remains in-memory only.
"""

from __future__ import annotations

import asyncio
import hashlib
import time

from apps.search.services.crawl.fetch_service import CrawlFetchService
from core.logging import get_logger
from core.search.live_fetch import FetchedPage

logger = get_logger(__name__)


def _make_failed_page(url: str, error: str, elapsed_ms: int) -> FetchedPage:
    return FetchedPage(
        source_url=url,
        canonical_url=url,
        markdown="",
        content_hash="",
        fetch_transport="failed",
        fetch_ms=elapsed_ms,
        error=error,
    )


class LiveFetchService:
    """Parallel live-gather for research orchestrator.

    Delegates HTTP + browser fetching to CrawlFetchService.
    Never calls rag_client.ingest_text.
    """

    def __init__(
        self,
        *,
        crawl_fetch_service: CrawlFetchService,
        min_extract_chars: int = 200,
    ) -> None:
        self._crawl_fetch: CrawlFetchService = crawl_fetch_service
        self._min_extract_chars: int = min_extract_chars

    async def fetch_one(
        self,
        url: str,
        *,
        timeout_ms: int = 8_000,
        browser_fallback: bool = True,
    ) -> FetchedPage:
        """Fetch a single URL; fallback to browser on HTTP failure."""
        timeout_seconds = timeout_ms / 1000.0
        started = time.perf_counter()
        try:
            result = await self._crawl_fetch.fetch_markdown(
                url,
                timeout_seconds=timeout_seconds,
                min_extract_chars=self._min_extract_chars,
                browser_fallback_enabled=browser_fallback,
            )
            elapsed = int((time.perf_counter() - started) * 1000)
            content_hash = hashlib.sha256(result.markdown.encode()).hexdigest()
            return FetchedPage(
                source_url=result.url,
                canonical_url=result.canonical_url,
                markdown=result.markdown,
                content_hash=content_hash,
                fetch_transport=result.fetch_transport,
                fetch_ms=elapsed,
            )
        except Exception as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            logger.debug("live_fetch failed url=%s error=%s", url, exc)
            return _make_failed_page(url, str(exc), elapsed)

    async def gather_many(
        self,
        urls: list[str],
        *,
        concurrency: int = 5,
        per_url_timeout_ms: int = 8_000,
        browser_fallback: bool = True,
    ) -> list[FetchedPage]:
        """Parallel fetch up to `concurrency` URLs simultaneously.

        Never raises — failed fetches return FetchedPage with fetch_transport='failed'.
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def _bounded(url: str) -> FetchedPage:
            async with semaphore:
                return await self.fetch_one(
                    url,
                    timeout_ms=per_url_timeout_ms,
                    browser_fallback=browser_fallback,
                )

        tasks = [_bounded(url) for url in urls]
        return list(await asyncio.gather(*tasks))
