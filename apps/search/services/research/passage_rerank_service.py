"""Thin rerank wrapper for EvidencePassage[] (§4.5.3, Phase 3).

Calls the platform cross-encoder reranker via AIRerankerHTTPClient;
returns passages sorted by rerank_score desc, top-K only.

Does NOT use apply_rerank_after_retrieve (that operates on RAGSearchResult[]).
"""

from __future__ import annotations

from dataclasses import replace

from core.ai.rerank_client import AIRerankerClientError, AIRerankerHTTPClient
from core.logging import get_logger
from core.search.live_fetch import EvidencePassage

logger = get_logger(__name__)


class PassageRerankService:
    """Cross-encoder reranker for live-fetch EvidencePassage lists."""

    def __init__(
        self,
        *,
        rerank_endpoint_url: str,
        timeout_seconds: float = 60.0,
        cost_per_1m_tokens: float = 5.0,
        platform_markup: float = 1.1,
        billing_resource_id: str = "rerank",
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._endpoint_url: str = rerank_endpoint_url
        self._client: AIRerankerHTTPClient = AIRerankerHTTPClient(
            timeout_seconds=timeout_seconds,
            cost_per_1m_tokens=cost_per_1m_tokens,
            platform_markup=platform_markup,
            billing_resource_id=billing_resource_id,
            model=model,
            api_key=api_key,
        )

    async def rerank(
        self,
        query: str,
        passages: list[EvidencePassage],
        *,
        top_k: int = 10,
    ) -> list[EvidencePassage]:
        """Rerank passages with cross-encoder and return top-K sorted by score.

        On any reranker error falls back to the original order (truncated at top_k).
        """
        if not passages:
            return []

        texts = [_passage_text(p) for p in passages]
        try:
            scores = await self._client.rerank_scores(
                self._endpoint_url,
                query,
                texts,
            )
        except AIRerankerClientError as exc:
            logger.warning(
                "passage rerank failed (fallback to original order): status=%s detail=%s",
                exc.status_code,
                exc.detail,
            )
            return passages[:top_k]
        except Exception as exc:
            logger.warning("passage rerank unexpected error (fallback): %s", exc)
            return passages[:top_k]

        scored: list[EvidencePassage] = [
            replace(p, rerank_score=score) for p, score in zip(passages, scores)
        ]
        scored.sort(key=lambda p: p.rerank_score or 0.0, reverse=True)
        return scored[:top_k]


def _passage_text(p: EvidencePassage) -> str:
    """Build rerank input string from passage (heading context + body)."""
    parts: list[str] = []
    if p.heading_trail:
        parts.append(" > ".join(p.heading_trail))
    elif p.section_title:
        parts.append(p.section_title)
    if p.text:
        parts.append(p.text)
    return "\n".join(parts).strip()
