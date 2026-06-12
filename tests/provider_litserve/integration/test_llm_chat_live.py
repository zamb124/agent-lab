"""Live LitServe chat completions with real transformers weights."""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(300, func_only=True),
]

_CHAT_PAYLOAD = {
    "model": "qwen/qwen2.5-1.5b-instruct-crawl",
    "messages": [
        {"role": "user", "content": "Reply with JSON: {\"answer\": \"ok\"}"},
    ],
    "temperature": 0.0,
    "max_tokens": 64,
    "response_format": {"type": "json_object"},
}


@pytest.mark.asyncio
async def test_llm_chat_completions_live(provider_litserve_crawl_llm_service):
    _ = provider_litserve_crawl_llm_service
    if os.getenv("CRAWL__E2E_LITSERVE_LLM") != "1":
        pytest.skip("CRAWL__E2E_LITSERVE_LLM=1 required")
    async with httpx.AsyncClient(base_url="http://localhost:9022", timeout=120.0) as client:
        health = await client.get("/v1/health/inference")
        assert health.status_code == 200
        response = await client.post("/v1/chat/completions", json=_CHAT_PAYLOAD)
        assert response.status_code == 200
        payload = response.json()
        assert payload["choices"][0]["message"]["content"]
