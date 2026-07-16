"""Async salient term extraction with KeyBERT (litserve) + local fallback."""

from __future__ import annotations

from core.ai.keybert_client import AIKeybertClientError, AIKeybertHTTPClient
from core.config import get_settings
from core.config.openai_v1_base_url import normalize_openai_v1_base_url
from core.logging import get_logger
from core.rag.openai_http_contracts import (
    PROVIDER_LITSERVE_PLACEHOLDER_BEARER,
    provider_litserve_keybert_http_url,
)
from core.search.pointer_models import RunetPointerConfig, SalientTermsConfig
from core.search.salient_terms import (
    extract_local_statistical_terms,
    extract_priority_terms,
    markdown_plain_for_keybert,
    merge_salient_terms,
)

logger = get_logger(__name__)


class SalientTermsService:
    def __init__(
        self,
        *,
        runet_config: RunetPointerConfig,
        keybert_client: AIKeybertHTTPClient | None = None,
    ) -> None:
        self._runet_config: RunetPointerConfig = runet_config
        self._keybert_client: AIKeybertHTTPClient = keybert_client or AIKeybertHTTPClient(
            api_key=PROVIDER_LITSERVE_PLACEHOLDER_BEARER,
        )

    async def extract(self, markdown: str, *, max_terms: int | None = None) -> list[str]:
        cap = max_terms if max_terms is not None else self._runet_config.salient_terms_max
        cfg = self._runet_config.salient_terms
        priority = extract_priority_terms(markdown)

        if cfg.backend == "local":
            statistical = extract_local_statistical_terms(
                markdown,
                max_terms=max(cap - len(priority), 0),
            )
            return merge_salient_terms(
                priority_terms=priority,
                statistical_terms=statistical,
                max_terms=cap,
            )

        statistical = await self._extract_keybert_statistical(markdown, cfg=cfg, max_terms=cap)
        return merge_salient_terms(
            priority_terms=priority,
            statistical_terms=statistical,
            max_terms=cap,
        )

    async def _extract_keybert_statistical(
        self,
        markdown: str,
        *,
        cfg: SalientTermsConfig,
        max_terms: int,
    ) -> list[str]:
        plain = markdown_plain_for_keybert(markdown)
        if len(plain) > cfg.max_input_chars:
            plain = plain[: cfg.max_input_chars]

        top_n = min(cfg.keybert_top_n, max(max_terms, 8))
        try:
            keywords = await self._keybert_client.extract_keywords(
                self._resolve_keybert_url(cfg),
                plain,
                top_n=top_n,
                use_mmr=cfg.keybert_use_mmr,
                diversity=cfg.keybert_diversity,
                model=self._resolve_keybert_model(cfg),
            )
            return [term for term, _score in keywords]
        except AIKeybertClientError as exc:
            if not cfg.fallback_to_local:
                raise
            logger.warning(
                "KeyBERT salient terms failed (status=%s), falling back to local TF: %s",
                exc.status_code,
                exc.detail,
            )
            return extract_local_statistical_terms(
                markdown,
                max_terms=max(max_terms, 0),
            )

    def _resolve_keybert_model(self, cfg: SalientTermsConfig) -> str | None:
        if cfg.keybert_model is not None and cfg.keybert_model.strip():
            return cfg.keybert_model.strip()
        infra_model = get_settings().provider_litserve.infra.keybert_openai_model_id.strip()
        return infra_model or None

    def _resolve_keybert_url(self, cfg: SalientTermsConfig) -> str:
        if cfg.litserve_base_url is not None and cfg.litserve_base_url.strip():
            base = normalize_openai_v1_base_url(cfg.litserve_base_url.strip())
        else:
            base = get_settings().provider_litserve.resolve_openai_v1_base_url()
        return provider_litserve_keybert_http_url(base)
