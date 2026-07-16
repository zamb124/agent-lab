"""ResearchOrchestratorService: Phase 3 research pipeline (§4.5, §5.3).

Pipeline:
  1. Discover top-N unique URLs from pointer-index via SearchClient.
  2. Parallel gather (LiveFetchService.gather_many).
  3. Fast heading-split → EvidencePassage[] (live_passage_split).
  4. Cross-encoder rerank on-the-fly (PassageRerankService).
  5. CRAG-lite sufficiency check → status.
  6. Return ResearchResult (no persist to vector_documents).

DoD:
  - 5+ URL parallel gather + rerank top-10 passages.
  - Zero fetched bytes written to persistent RAG storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from apps.search.services.research.live_fetch_service import LiveFetchService
from apps.search.services.research.passage_rerank_service import PassageRerankService
from core.clients.search_client import SearchClient
from core.clients.service_client import ServiceClientError
from core.logging import get_logger
from core.search.live_fetch import EvidencePassage, FetchedPage
from core.search.live_passage_split import split_pages_to_passages
from core.search.models import MetaSearchRequest, WebSearchResult
from core.search.pointer_models import RunetResearchPoolConfig

logger = get_logger(__name__)

ResearchStatus = Literal["done", "partial", "no_results", "index_error", "fetch_error"]


@dataclass
class ResearchResult:
    """Output of ResearchOrchestratorService.research()."""

    query: str
    status: ResearchStatus
    candidates: list[WebSearchResult] = field(default_factory=list)
    fetched: list[FetchedPage] = field(default_factory=list)
    passages: list[EvidencePassage] = field(default_factory=list)
    evidence: list[EvidencePassage] = field(default_factory=list)
    index_ids: list[str] = field(default_factory=list)
    fetch_success_count: int = 0
    fetch_failure_count: int = 0
    total_passages_before_rerank: int = 0
    error: str | None = None

    def to_json_summary(self) -> dict[str, object]:
        """Compact serializable summary for flow tools."""
        return {
            "status": self.status,
            "query": self.query,
            "candidates_count": len(self.candidates),
            "fetch_success": self.fetch_success_count,
            "fetch_failure": self.fetch_failure_count,
            "passages_total": self.total_passages_before_rerank,
            "evidence_count": len(self.evidence),
            "evidence": [_evidence_to_dict(e) for e in self.evidence],
            "sources": [_candidate_to_dict(c) for c in self.candidates],
            "error": self.error,
        }


class ResearchOrchestratorService:
    """Orchestrates the Phase-3 research pipeline.

    Never calls rag_client.ingest_text — all markdown stays in-memory.
    """

    def __init__(
        self,
        *,
        live_fetch_service: LiveFetchService,
        passage_rerank_service: PassageRerankService | None,
        pool_config: RunetResearchPoolConfig,
        search_client: SearchClient | None = None,
    ) -> None:
        self._live_fetch: LiveFetchService = live_fetch_service
        self._rerank: PassageRerankService | None = passage_rerank_service
        self._pool: RunetResearchPoolConfig = pool_config
        self._search_client: SearchClient = search_client or SearchClient()

    async def research(
        self,
        query: str,
        *,
        index_ids: list[str] | None = None,
        limit: int | None = None,
    ) -> ResearchResult:
        """Execute full research pipeline for a query.

        Parameters
        ----------
        query:
            User search query.
        index_ids:
            RAG index slugs to query (defaults to ["runet"]).
        limit:
            Max URLs to fetch (capped by pool_config.max_urls).
        """
        effective_index_ids = index_ids or ["runet"]
        max_urls = min(limit or self._pool.max_urls, self._pool.max_urls)

        # Step 1: Discover top-N unique URLs via pointer index
        candidates, index_error = await self._discover(
            query,
            index_ids=effective_index_ids,
            limit=max_urls,
        )
        if index_error:
            return ResearchResult(
                query=query,
                status="index_error",
                index_ids=effective_index_ids,
                error=index_error,
            )
        if not candidates:
            return ResearchResult(
                query=query,
                status="no_results",
                index_ids=effective_index_ids,
            )

        urls = [c.url for c in candidates]
        focus_hints = {
            (c.canonical_url or c.url): c.section_title
            for c in candidates
            if c.section_title
        }

        # Step 2: Parallel gather
        fetched_pages = await self._live_fetch.gather_many(
            urls,
            concurrency=self._pool.fetch_concurrency,
            per_url_timeout_ms=self._pool.per_url_timeout_ms,
        )
        ok_pages = [p for p in fetched_pages if p.ok]
        fail_count = len(fetched_pages) - len(ok_pages)

        if not ok_pages:
            return ResearchResult(
                query=query,
                status="fetch_error",
                candidates=candidates,
                fetched=fetched_pages,
                fetch_success_count=0,
                fetch_failure_count=fail_count,
                index_ids=effective_index_ids,
                error="all URLs failed to fetch",
            )

        # Step 3: Fast heading-split → passages
        all_passages = split_pages_to_passages(
            ok_pages,
            max_passage_tokens=self._pool.max_passage_tokens,
            max_passages_per_url=self._pool.max_passages_per_url,
            max_passages_total=self._pool.max_passages_total,
            focus_hints=focus_hints,
        )
        total_before_rerank = len(all_passages)

        # Step 4: Cross-encoder rerank on-the-fly
        evidence = await self._rerank_passages(query, all_passages)

        # Step 5: CRAG-lite sufficiency check
        status = _crag_lite_status(evidence, ok_pages)

        return ResearchResult(
            query=query,
            status=status,
            candidates=candidates,
            fetched=fetched_pages,
            passages=all_passages,
            evidence=evidence,
            index_ids=effective_index_ids,
            fetch_success_count=len(ok_pages),
            fetch_failure_count=fail_count,
            total_passages_before_rerank=total_before_rerank,
        )

    async def _discover(
        self,
        query: str,
        *,
        index_ids: list[str],
        limit: int,
    ) -> tuple[list[WebSearchResult], str | None]:
        """Query pointer-index; return (results, error_or_None)."""
        try:
            response = await self._search_client.search(
                MetaSearchRequest(
                    query=query,
                    limit=limit,
                    providers=["index"],
                    index_ids=index_ids,
                    mode="quick",
                )
            )
        except ServiceClientError as exc:
            logger.warning("research discover failed: %s", exc)
            return [], str(exc)
        except Exception as exc:
            logger.warning("research discover unexpected error: %s", exc)
            return [], str(exc)

        results = list(response.results)
        if not results:
            return [], None

        # Dedup by canonical_url already done by IndexSearchProvider, but guard
        seen: dict[str, WebSearchResult] = {}
        for r in results:
            key = r.canonical_url or r.url
            if key not in seen or r.score > seen[key].score:
                seen[key] = r
        return list(seen.values()), None

    async def _rerank_passages(
        self,
        query: str,
        passages: list[EvidencePassage],
    ) -> list[EvidencePassage]:
        if not passages:
            return []
        if self._rerank is None:
            return passages[: self._pool.rerank_top_k]
        return await self._rerank.rerank(
            query,
            passages,
            top_k=self._pool.rerank_top_k,
        )


def _crag_lite_status(
    evidence: list[EvidencePassage],
    ok_pages: list[FetchedPage],
) -> ResearchStatus:
    """Lightweight CRAG-inspired evaluator (§4.5.3).

    Returns 'done' if we have evidence, 'partial' if pages fetched but
    no good evidence after rerank, 'fetch_error' otherwise.
    """
    if evidence:
        return "done"
    if ok_pages:
        return "partial"
    return "fetch_error"


def _evidence_to_dict(e: EvidencePassage) -> dict[str, object]:
    return {
        "source_url": e.source_url,
        "section_title": e.section_title,
        "heading_trail": e.heading_trail,
        "text": e.text,
        "rerank_score": e.rerank_score,
        "char_start": e.char_start,
    }


def _candidate_to_dict(c: WebSearchResult) -> dict[str, object]:
    return {
        "title": c.title,
        "url": c.url,
        "canonical_url": c.canonical_url,
        "snippet": c.snippet,
        "section_title": c.section_title,
        "salient_terms": c.salient_terms,
        "score": c.score,
        "indexed_at": c.indexed_at,
    }
