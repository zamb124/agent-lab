from __future__ import annotations

import pytest
from a2a.helpers.proto_helpers import get_message_text

from core.ai.free_pool import (
    PlatformFreeModelRecord,
    serialize_platform_free_models,
)
from core.ai.llm_config import LLMCallConfig
from core.ai.providers import HUMANITEC_LLM_AUTO_MODEL, HUMANITEC_LLM_PROVIDER
from core.clients.llm.platform_pool import _make_humanitec_llms_candidate_chain_resolver
from core.clients.llm.runtime import create_llm_transport_client
from core.clients.redis_client import RedisClient
from core.config import BaseSettings, get_settings, set_settings
from core.config.models import (
    CerebrasProviderConfig,
    LLMConfig,
    OpenAIProviderConfig,
    OpenRouterProviderConfig,
    PlatformFreePoolConfig,
    PlatformFreePoolPaidFallbackConfig,
)
from tests.core.clients.test_llm_candidate_fallback_integration import (
    _message,
    _OpenAICompatibleTestServer,
    _production_llm_env,
    _write_sse_text,
)


def _groq_record(*, unique_id: str) -> PlatformFreeModelRecord:
    return PlatformFreeModelRecord(
        provider="groq",
        id=f"llama-{unique_id}",
        score=20.0,
        context_length=8192,
        supported_parameters=("tools",),
        input_modalities=("text",),
        output_modalities=("text",),
        free_reason="account_free_tier",
    )


@pytest.fixture
def platform_free_cache_key(unique_id: str, monkeypatch: pytest.MonkeyPatch) -> str:
    key = f"llm:platform:free_models:expand:{unique_id}"
    monkeypatch.setattr("core.ai.free_pool.PLATFORM_FREE_MODELS_CACHE_KEY", key)
    monkeypatch.setattr("core.clients.llm.platform_pool.PLATFORM_FREE_MODELS_CACHE_KEY", key)
    monkeypatch.setattr("core.clients.llm.platform_pool._platform_free_pool_redis", None)
    return key


def _expand_settings(
    *,
    paid: bool,
    groq_key: str | None = None,
    groq_api_keys: list[str] | None = None,
) -> BaseSettings:
    live = get_settings()
    if live.llm.groq is None:
        raise ValueError("llm.groq обязателен для expand-тестов")
    paid_fallback = PlatformFreePoolPaidFallbackConfig(
        provider="openrouter",
        model="qwen/qwen-2.5-7b-instruct",
    )
    return live.model_copy(
        update={
            "llm": live.llm.model_copy(
                update={
                    "openrouter": OpenRouterProviderConfig(
                        api_key="sk-openrouter" if paid else None,
                        base_url="https://openrouter.ai/api/v1",
                        site_url="https://platform.example",
                        site_name="Platform Test",
                    ),
                    "openai": OpenAIProviderConfig(
                        api_key="sk-openai",
                        base_url="https://api.openai.example/v1",
                    ),
                    "groq": live.llm.groq.model_copy(
                        update={"api_key": groq_key, "api_keys": groq_api_keys}
                    ),
                    "cerebras": CerebrasProviderConfig(api_key=None),
                    "platform_free_pool": PlatformFreePoolConfig(
                        enabled=True,
                        paid_fallback=paid_fallback,
                    ),
                }
            )
        }
    )


@pytest.mark.asyncio
async def test_auto_empty_redis_without_fallbacks_raises(
    platform_free_cache_key: str,
) -> None:
    _ = platform_free_cache_key
    settings = _expand_settings(paid=False)
    resolver = _make_humanitec_llms_candidate_chain_resolver(
        LLMCallConfig(provider=HUMANITEC_LLM_PROVIDER, model=HUMANITEC_LLM_AUTO_MODEL),
        None,
        settings=settings,
        state=None,
        include_paid_fallback=False,
    )
    with pytest.raises(RuntimeError, match="humanitec_llm auto: нет кандидатов"):
        await resolver()


@pytest.mark.asyncio
async def test_auto_empty_redis_with_paid_fallback(
    platform_free_cache_key: str,
) -> None:
    _ = platform_free_cache_key
    settings = _expand_settings(paid=True)
    resolver = _make_humanitec_llms_candidate_chain_resolver(
        LLMCallConfig(provider=HUMANITEC_LLM_PROVIDER, model=HUMANITEC_LLM_AUTO_MODEL),
        None,
        settings=settings,
        state=None,
        include_paid_fallback=True,
    )
    candidates = await resolver()
    assert [row.source for row in candidates] == ["platform_paid_fallback"]
    assert candidates[0].model == "qwen/qwen-2.5-7b-instruct"


@pytest.mark.asyncio
async def test_auto_empty_redis_uses_authored_fallback(
    platform_free_cache_key: str,
) -> None:
    _ = platform_free_cache_key
    settings = _expand_settings(paid=False)
    resolver = _make_humanitec_llms_candidate_chain_resolver(
        LLMCallConfig(provider=HUMANITEC_LLM_PROVIDER, model=HUMANITEC_LLM_AUTO_MODEL),
        [
            LLMCallConfig(
                provider="openai",
                model="gpt-4o-mini",
                api_key="sk-openai",
                base_url="https://api.openai.example/v1",
            )
        ],
        settings=settings,
        state=None,
        include_paid_fallback=False,
    )
    candidates = await resolver()
    assert [(row.provider, row.model) for row in candidates] == [("openai", "gpt-4o-mini")]
    assert candidates[0].source == "fallback"


@pytest.mark.asyncio
async def test_empty_humanitec_fallback_skips_to_openai(
    platform_free_cache_key: str,
) -> None:
    _ = platform_free_cache_key
    settings = _expand_settings(paid=False)
    resolver = _make_humanitec_llms_candidate_chain_resolver(
        LLMCallConfig(provider=HUMANITEC_LLM_PROVIDER, model=HUMANITEC_LLM_AUTO_MODEL),
        [
            LLMCallConfig(provider=HUMANITEC_LLM_PROVIDER, model=HUMANITEC_LLM_AUTO_MODEL),
            LLMCallConfig(
                provider="openai",
                model="gpt-4o-mini",
                api_key="sk-openai",
                base_url="https://api.openai.example/v1",
            ),
        ],
        settings=settings,
        state=None,
        include_paid_fallback=False,
    )
    candidates = await resolver()
    assert [(row.provider, row.model) for row in candidates] == [("openai", "gpt-4o-mini")]


@pytest.mark.asyncio
async def test_pinned_missing_without_fallback_raises(
    platform_free_cache_key: str,
) -> None:
    _ = platform_free_cache_key
    settings = _expand_settings(paid=False)
    resolver = _make_humanitec_llms_candidate_chain_resolver(
        LLMCallConfig(provider=HUMANITEC_LLM_PROVIDER, model="groq:missing-id"),
        None,
        settings=settings,
        state=None,
        include_paid_fallback=False,
    )
    with pytest.raises(RuntimeError, match="не найден в verified free-pool cache"):
        await resolver()


@pytest.mark.asyncio
async def test_pinned_missing_uses_authored_fallback(
    platform_free_cache_key: str,
) -> None:
    _ = platform_free_cache_key
    settings = _expand_settings(paid=False)
    resolver = _make_humanitec_llms_candidate_chain_resolver(
        LLMCallConfig(provider=HUMANITEC_LLM_PROVIDER, model="groq:missing-id"),
        [
            LLMCallConfig(
                provider="openai",
                model="gpt-4o-mini",
                api_key="sk-openai",
                base_url="https://api.openai.example/v1",
            )
        ],
        settings=settings,
        state=None,
        include_paid_fallback=False,
    )
    candidates = await resolver()
    assert candidates[0].provider == "openai"
    assert candidates[0].model == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_records_without_api_key_are_skipped(
    platform_free_cache_key: str,
    unique_id: str,
) -> None:
    redis_client = RedisClient(get_settings().database.redis_url)
    wrote = await redis_client.set(
        platform_free_cache_key,
        serialize_platform_free_models([_groq_record(unique_id=unique_id)]),
        ttl=120,
    )
    assert wrote is True
    settings = _expand_settings(paid=False, groq_key=None)
    resolver = _make_humanitec_llms_candidate_chain_resolver(
        LLMCallConfig(provider=HUMANITEC_LLM_PROVIDER, model=HUMANITEC_LLM_AUTO_MODEL),
        None,
        settings=settings,
        state=None,
        include_paid_fallback=False,
    )
    with pytest.raises(RuntimeError, match="humanitec_llm auto: нет кандидатов"):
        await resolver()


@pytest.mark.asyncio
async def test_paid_disabled_still_uses_authored_fallback(
    platform_free_cache_key: str,
) -> None:
    _ = platform_free_cache_key
    settings = _expand_settings(paid=True)
    resolver = _make_humanitec_llms_candidate_chain_resolver(
        LLMCallConfig(provider=HUMANITEC_LLM_PROVIDER, model=HUMANITEC_LLM_AUTO_MODEL),
        [
            LLMCallConfig(
                provider="openai",
                model="gpt-4o-mini",
                api_key="sk-openai",
                base_url="https://api.openai.example/v1",
            )
        ],
        settings=settings,
        state=None,
        include_paid_fallback=False,
    )
    candidates = await resolver()
    assert [row.source for row in candidates] == ["fallback"]
    assert candidates[0].provider == "openai"


@pytest.mark.asyncio
async def test_empty_models_snapshot_uses_authored_fallback(
    platform_free_cache_key: str,
) -> None:
    redis_client = RedisClient(get_settings().database.redis_url)
    wrote = await redis_client.set(
        platform_free_cache_key,
        serialize_platform_free_models([]),
        ttl=120,
    )
    assert wrote is True
    settings = _expand_settings(paid=False)
    resolver = _make_humanitec_llms_candidate_chain_resolver(
        LLMCallConfig(provider=HUMANITEC_LLM_PROVIDER, model=HUMANITEC_LLM_AUTO_MODEL),
        [
            LLMCallConfig(
                provider="openai",
                model="gpt-4o-mini",
                api_key="sk-openai",
                base_url="https://api.openai.example/v1",
            )
        ],
        settings=settings,
        state=None,
        include_paid_fallback=False,
    )
    candidates = await resolver()
    assert [(row.provider, row.model) for row in candidates] == [("openai", "gpt-4o-mini")]


@pytest.mark.asyncio
async def test_empty_redis_authored_fallback_http_only_openai(
    platform_free_cache_key: str,
    unique_id: str,
) -> None:
    _ = platform_free_cache_key
    fallback_model = f"openai-fallback-{unique_id}"
    server = _OpenAICompatibleTestServer(
        {fallback_model: lambda writer: _write_sse_text(writer, "openai-ok")}
    )
    await server.start()
    old_settings = get_settings()
    settings = old_settings.model_copy(
        update={
            "testing": False,
            "llm": LLMConfig(
                provider=HUMANITEC_LLM_PROVIDER,
                default_model=HUMANITEC_LLM_AUTO_MODEL,
                openai=OpenAIProviderConfig(
                    api_key="sk-openai",
                    base_url=server.base_url,
                ),
                platform_free_pool=PlatformFreePoolConfig(enabled=True),
            ),
        }
    )
    try:
        set_settings(settings)
        with _production_llm_env():
            client = create_llm_transport_client(
                provider=HUMANITEC_LLM_PROVIDER,
                model_name=HUMANITEC_LLM_AUTO_MODEL,
                fallback_models=[
                    LLMCallConfig(
                        provider="openai",
                        model=fallback_model,
                        api_key="sk-openai",
                        base_url=server.base_url,
                    )
                ],
                allow_platform_paid_fallback=False,
            )
            message = await client.chat([_message("hello")])
        assert get_message_text(message) == "openai-ok"
        assert [request.model for request in server.requests] == [fallback_model]
    finally:
        set_settings(old_settings)
        await server.close()


@pytest.mark.asyncio
async def test_corrupt_cache_raises_and_does_not_use_fallback(
    platform_free_cache_key: str,
) -> None:
    redis_client = RedisClient(get_settings().database.redis_url)
    wrote = await redis_client.set(platform_free_cache_key, "{bad-json", ttl=120)
    assert wrote is True
    settings = _expand_settings(paid=False)
    resolver = _make_humanitec_llms_candidate_chain_resolver(
        LLMCallConfig(provider=HUMANITEC_LLM_PROVIDER, model=HUMANITEC_LLM_AUTO_MODEL),
        [
            LLMCallConfig(
                provider="openai",
                model="gpt-4o-mini",
                api_key="sk-openai",
                base_url="https://api.openai.example/v1",
            )
        ],
        settings=settings,
        state=None,
        include_paid_fallback=False,
    )
    with pytest.raises(ValueError):
        await resolver()


def test_constructor_without_pool_and_without_fallbacks_raises() -> None:
    old_settings = get_settings()
    settings = BaseSettings(
        testing=False,
        llm=LLMConfig(
            provider=HUMANITEC_LLM_PROVIDER,
            default_model=HUMANITEC_LLM_AUTO_MODEL,
            platform_free_pool=PlatformFreePoolConfig(enabled=True),
        ),
    )
    try:
        set_settings(settings)
        with _production_llm_env():
            with pytest.raises(ValueError, match="humanitec_llm недоступен"):
                create_llm_transport_client(
                    provider=HUMANITEC_LLM_PROVIDER,
                    model_name=HUMANITEC_LLM_AUTO_MODEL,
                )
    finally:
        set_settings(old_settings)


def test_constructor_without_pool_uses_authored_fallback() -> None:
    old_settings = get_settings()
    settings = BaseSettings(
        testing=False,
        llm=LLMConfig(
            provider=HUMANITEC_LLM_PROVIDER,
            default_model=HUMANITEC_LLM_AUTO_MODEL,
            openai=OpenAIProviderConfig(
                api_key="sk-openai",
                base_url="https://api.openai.example/v1",
            ),
            platform_free_pool=PlatformFreePoolConfig(enabled=True),
        ),
    )
    try:
        set_settings(settings)
        with _production_llm_env():
            client = create_llm_transport_client(
                provider=HUMANITEC_LLM_PROVIDER,
                model_name=HUMANITEC_LLM_AUTO_MODEL,
                fallback_models=[
                    LLMCallConfig(
                        provider="openai",
                        model="gpt-4o-mini",
                        api_key="sk-openai",
                        base_url="https://api.openai.example/v1",
                    )
                ],
                allow_platform_paid_fallback=False,
            )
    finally:
        set_settings(old_settings)
    assert client.model == "gpt-4o-mini"
    assert client.llm_provider == "openai"
    assert client._candidate_resolver is not None


@pytest.mark.asyncio
async def test_auto_expands_one_model_per_api_key(
    platform_free_cache_key: str,
    unique_id: str,
) -> None:
    redis_client = RedisClient(get_settings().database.redis_url)
    record = _groq_record(unique_id=unique_id)
    wrote = await redis_client.set(
        platform_free_cache_key,
        serialize_platform_free_models([record]),
        ttl=120,
    )
    assert wrote is True
    settings = _expand_settings(
        paid=False,
        groq_key="sk-main",
        groq_api_keys=["sk-extra-a", "sk-extra-b"],
    )
    resolver = _make_humanitec_llms_candidate_chain_resolver(
        LLMCallConfig(provider=HUMANITEC_LLM_PROVIDER, model=HUMANITEC_LLM_AUTO_MODEL),
        None,
        settings=settings,
        state=None,
        include_paid_fallback=False,
    )
    candidates = await resolver()
    assert [row.api_key for row in candidates] == ["sk-main", "sk-extra-a", "sk-extra-b"]
    assert all(row.provider == "groq" and row.model == record.id for row in candidates)
