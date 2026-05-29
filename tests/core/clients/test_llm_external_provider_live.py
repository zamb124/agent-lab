"""Live checks for configured external OpenAI-compatible LLM providers.

These tests intentionally hit real provider APIs. They are skipped when a
provider key is absent or still a placeholder, and fail loudly for revoked keys,
stale model catalogs, unsupported smoke models, or broken chat completions.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from a2a.types import Message, Part, Role, TextPart

from apps.flows.src.db.llm_model_repository import LLMModelRepository
from apps.flows.src.services.llm_models_service import LLMModelsService
from core.clients.llm.factory import LLMClient, get_llm
from core.clients.llm.model_routing import (
    ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS,
    OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
)
from core.config import get_settings

pytestmark = [pytest.mark.network, pytest.mark.timeout(120)]

_LIVE_PROVIDERS = tuple(
    provider
    for provider in OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER
    if provider in ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS or provider == "deepinfra"
)
_PLACEHOLDER_PREFIXES = ("YOUR_",)
_EXPECTED_MARKER = "PONG42"


def _skip_provider_rate_limit(provider: str, exc: httpx.HTTPStatusError) -> None:
    if exc.response.status_code != 429:
        return
    retry_after = exc.response.headers.get("retry-after")
    suffix = f"; retry-after={retry_after}" if retry_after else ""
    pytest.skip(f"{provider}: provider rate limit 429{suffix}")


@contextmanager
def _disable_testing_mode() -> Iterator[None]:
    old_testing = os.environ.get("TESTING")
    old_pytest = os.environ.pop("PYTEST_CURRENT_TEST", None)
    old_pytest_raise = os.environ.pop("_PYTEST_RAISE", None)
    os.environ["TESTING"] = "false"
    try:
        yield
    finally:
        if old_testing is None:
            os.environ.pop("TESTING", None)
        else:
            os.environ["TESTING"] = old_testing
        if old_pytest is not None:
            os.environ["PYTEST_CURRENT_TEST"] = old_pytest
        if old_pytest_raise is not None:
            os.environ["_PYTEST_RAISE"] = old_pytest_raise


def _message(text: str) -> Message:
    return Message(
        messageId=str(uuid.uuid4()),
        role=Role.user,
        parts=[Part(root=TextPart(text=text))],
    )


def _configured_provider(provider: str) -> object:
    cfg = getattr(get_settings().llm, provider, None)
    api_key = getattr(cfg, "api_key", None)
    if cfg is None or not isinstance(api_key, str) or not api_key.strip():
        pytest.skip(f"{provider}: api_key не настроен")
    if api_key.startswith(_PLACEHOLDER_PREFIXES):
        pytest.skip(f"{provider}: api_key остался placeholder")
    return cfg


def _smoke_model(provider: str) -> str:
    cfg = _configured_provider(provider)
    smoke_model = getattr(cfg, "smoke_model", None)
    if not isinstance(smoke_model, str) or not smoke_model.strip():
        pytest.fail(f"{provider}: llm.{provider}.smoke_model должен быть непустой строкой")
    return smoke_model.strip()


def _catalog_id_for_smoke_model(smoke_model: str) -> str:
    return smoke_model.split(":", 1)[0]


@pytest.mark.parametrize("provider", _LIVE_PROVIDERS)
async def test_live_provider_model_catalog_returns_configured_smoke_model(provider: str) -> None:
    _ = _configured_provider(provider)
    service = LLMModelsService(MagicMock(spec=LLMModelRepository), AsyncMock(), AsyncMock())

    try:
        models = await service.fetch_models_by_provider(provider)
    except httpx.HTTPStatusError as exc:
        _skip_provider_rate_limit(provider, exc)
        raise

    assert isinstance(models, list)
    assert models, f"{provider}: models catalog вернул пустой список"
    assert all(isinstance(model_id, str) and model_id.strip() for model_id in models)

    expected_model_id = _catalog_id_for_smoke_model(_smoke_model(provider))
    assert expected_model_id in models, (
        f"{provider}: smoke_model={expected_model_id!r} отсутствует в live catalog"
    )


@pytest.mark.parametrize("provider", _LIVE_PROVIDERS)
async def test_live_provider_chat_completion_smoke(provider: str) -> None:
    _ = _configured_provider(provider)
    model = _smoke_model(provider)
    prompt = f"Reply with exactly {_EXPECTED_MARKER} and no other text."

    with _disable_testing_mode():
        llm = get_llm(
            model_name=model,
            provider=provider,
            temperature=0.0,
            max_tokens=12,
        )

    assert isinstance(llm, LLMClient)
    assert llm.llm_provider == provider

    try:
        result = await llm.invoke([_message(prompt)], max_tokens=12)
    except httpx.HTTPStatusError as exc:
        _skip_provider_rate_limit(provider, exc)
        if exc.response.status_code == 402:
            pytest.fail(
                f"{provider}: catalog доступен, но inference требует положительный баланс"
            )
        raise

    assert isinstance(result, str)
    assert _EXPECTED_MARKER in result.strip(), (
        f"{provider}: smoke completion must contain {_EXPECTED_MARKER!r}, got {result!r}"
    )
