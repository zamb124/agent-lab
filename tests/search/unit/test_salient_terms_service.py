"""Tests for SalientTermsService (KeyBERT + local fallback)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from apps.search.services.crawl.salient_terms_service import SalientTermsService
from core.ai.keybert_client import AIKeybertClientError, AIKeybertHTTPClient
from core.search.pointer_models import RunetPointerConfig, SalientTermsConfig


@pytest.mark.asyncio
async def test_local_backend_uses_tf_without_http() -> None:
    config = RunetPointerConfig(
        salient_terms=SalientTermsConfig(backend="local"),
    )
    client = AsyncMock(spec=AIKeybertHTTPClient)
    service = SalientTermsService(runet_config=config, keybert_client=client)
    terms = await service.extract(
        "# Kubernetes\n\nDeploy Ingress with TLS cert-manager.\n",
        max_terms=20,
    )
    client.extract_keywords.assert_not_called()
    assert any("Kubernetes" in t or "Ingress" in t for t in terms)


@pytest.mark.asyncio
async def test_keybert_backend_merges_priority_and_keybert() -> None:
    config = RunetPointerConfig(
        salient_terms=SalientTermsConfig(backend="keybert", fallback_to_local=False),
    )
    client = AsyncMock(spec=AIKeybertHTTPClient)
    client.extract_keywords = AsyncMock(
        return_value=[("cert-manager", 0.9), ("ingress controller", 0.8)],
    )
    service = SalientTermsService(runet_config=config, keybert_client=client)
    md = "# Security\n\nFixed CVE-2024-1234 in OpenSSL deployment.\n"
    terms = await service.extract(md, max_terms=20)
    assert "CVE-2024-1234" in terms
    assert "cert-manager" in terms
    client.extract_keywords.assert_awaited_once()


@pytest.mark.asyncio
async def test_keybert_failure_falls_back_to_local() -> None:
    config = RunetPointerConfig(
        salient_terms=SalientTermsConfig(backend="keybert", fallback_to_local=True),
    )
    client = AsyncMock(spec=AIKeybertHTTPClient)
    client.extract_keywords = AsyncMock(
        side_effect=AIKeybertClientError(status_code=503, detail={"reason": "timeout"}),
    )
    service = SalientTermsService(runet_config=config, keybert_client=client)
    terms = await service.extract(
        "# PostgreSQL\n\nReplication lag monitoring with Prometheus.\n",
        max_terms=20,
    )
    assert len(terms) > 0
