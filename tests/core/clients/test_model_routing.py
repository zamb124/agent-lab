"""Контракт split_provider_prefixed_model (префикс платформенного провайдера в model)."""

import pytest
from pydantic import ValidationError

from core.ai.company_settings import PLATFORM_LLM_PROVIDERS
from core.ai.providers import (
    ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS,
    LINNEX_LLM_PROVIDER,
    LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER,
    OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
    PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER,
    PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS,
    PLATFORM_LLM_PROVIDER_ORDER,
    ZERO_PRICE_LLM_PROVIDER_SLUGS,
    linnex_llms_model_ref,
    split_linnex_llms_model_ref,
    split_provider_prefixed_model,
)
from core.config.models import PlatformFreePoolConfig, PlatformFreePoolPaidFallbackConfig


def test_split_when_provider_set_unchanged():
    assert split_provider_prefixed_model("openrouter", "openai/gpt-4o") == ("openrouter", "openai/gpt-4o")


def test_split_openrouter_vendor_model():
    assert split_provider_prefixed_model(None, "openrouter:openai/gpt-4o") == (
        "openrouter",
        "openai/gpt-4o",
    )


def test_split_openai_short_id():
    assert split_provider_prefixed_model("", "openai:gpt-4o") == ("openai", "gpt-4o")


def test_no_split_vendor_slash_only():
    assert split_provider_prefixed_model(None, "openai/gpt-4o") == (None, "openai/gpt-4o")


def test_no_split_unknown_head():
    assert split_provider_prefixed_model(None, "foo:bar") == (None, "foo:bar")


def test_no_split_empty_tail():
    assert split_provider_prefixed_model(None, "openrouter:") == (None, "openrouter:")


def test_no_split_only_colon():
    assert split_provider_prefixed_model(None, ":") == (None, ":")


def test_linnex_llms_model_ref_is_provider_prefixed_free_pool_model():
    assert (
        linnex_llms_model_ref("openrouter", "qwen/qwen3-coder:free")
        == "openrouter:qwen/qwen3-coder:free"
    )
    assert split_linnex_llms_model_ref("openrouter:qwen/qwen3-coder:free") == (
        "openrouter",
        "qwen/qwen3-coder:free",
    )
    assert split_linnex_llms_model_ref("auto") is None
    assert split_linnex_llms_model_ref("deepinfra:deepseek-ai/DeepSeek-V3") is None


@pytest.mark.parametrize(
    "slug",
    OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
)
def test_split_accepts_all_platform_slugs(slug: str):
    p, m = split_provider_prefixed_model(None, f"{slug}:x/y")
    assert p == slug
    assert m == "x/y"


def test_platform_free_pool_has_no_configured_provider_list():
    with pytest.raises(ValidationError):
        PlatformFreePoolConfig(providers=OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER)


def test_platform_free_pool_candidate_order_is_canonical():
    assert PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER == tuple(
        slug
        for slug in OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER
        if slug in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS
    )


@pytest.mark.parametrize("slug", OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER)
def test_platform_paid_fallback_accepts_all_platform_provider_slugs(slug: str):
    cfg = PlatformFreePoolPaidFallbackConfig(provider=slug, model="x/y")
    assert cfg.provider == slug


def test_user_platform_provider_order_is_canonical():
    assert PLATFORM_LLM_PROVIDER_ORDER == (
        LINNEX_LLM_PROVIDER,
        *OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
    )
    assert PLATFORM_LLM_PROVIDERS == PLATFORM_LLM_PROVIDER_ORDER


def test_free_model_policy_is_explicit_for_every_provider():
    assert tuple(LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER) == OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER
    assert LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER["openrouter"] == "zero_price_catalog"
    assert LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER["bothub"] == "zero_price_catalog"
    assert LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER["groq"] == "account_free_tier"
    assert LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER["cerebras"] == "account_free_tier"
    assert LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER["nvidia"] == "account_free_tier"
    assert LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER["mistral"] == "account_free_tier"
    assert LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER["zai"] == "account_free_tier"
    assert LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER["sambanova"] == "account_free_tier"
    assert PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS == (
        ZERO_PRICE_LLM_PROVIDER_SLUGS | ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS
    )


def test_candidate_key_includes_api_key_hash():
    from core.ai.llm_config import LLMCallConfig
    from core.clients.llm.candidates import candidate_key

    c1 = LLMCallConfig(
        provider="openrouter",
        model="model-a",
        base_url="https://example.com/v1",
        api_key="sk-key-a",
    )
    c2 = LLMCallConfig(
        provider="openrouter",
        model="model-a",
        base_url="https://example.com/v1",
        api_key="sk-key-b",
    )
    c3 = LLMCallConfig(
        provider="openrouter",
        model="model-a",
        base_url="https://example.com/v1",
    )

    key1 = candidate_key(c1)
    key2 = candidate_key(c2)
    key3 = candidate_key(c3)

    assert key1 != key2
    assert "nokey" in key3
    assert "openrouter:https://example.com/v1:model-a:" in key1
    assert "openrouter:https://example.com/v1:model-a:" in key2


def test_resolve_provider_api_keys_collects_main_and_extra_keys():
    from core.config.llm_openai_compat import resolve_provider_api_keys
    from core.config.models import (
        LLMConfig,
        OpenRouterProviderConfig,
    )

    llm = LLMConfig(
        provider="linnex_llm",
        openrouter=OpenRouterProviderConfig(
            api_key="sk-main",
            api_keys=["sk-extra-1", "sk-extra-2"],
            base_url="https://openrouter.ai/api/v1",
        ),
    )
    keys = resolve_provider_api_keys(llm, "openrouter")
    assert keys == ["sk-main", "sk-extra-1", "sk-extra-2"]


def test_resolve_provider_api_keys_deduplicates():
    from core.config.llm_openai_compat import resolve_provider_api_keys
    from core.config.models import (
        LLMConfig,
        OpenRouterProviderConfig,
    )

    llm = LLMConfig(
        provider="linnex_llm",
        openrouter=OpenRouterProviderConfig(
            api_key="sk-main",
            api_keys=["sk-main", "sk-extra"],
            base_url="https://openrouter.ai/api/v1",
        ),
    )
    keys = resolve_provider_api_keys(llm, "openrouter")
    assert keys == ["sk-main", "sk-extra"]


def test_resolve_provider_api_keys_only_api_key():
    from core.config.llm_openai_compat import resolve_provider_api_keys
    from core.config.models import (
        LLMConfig,
        OpenRouterProviderConfig,
    )

    llm = LLMConfig(
        provider="linnex_llm",
        openrouter=OpenRouterProviderConfig(
            api_key="sk-main",
            base_url="https://openrouter.ai/api/v1",
        ),
    )
    keys = resolve_provider_api_keys(llm, "openrouter")
    assert keys == ["sk-main"]


def test_resolve_provider_api_keys_filters_empty_and_placeholders():
    from core.config.llm_openai_compat import resolve_provider_api_keys
    from core.config.models import (
        LLMConfig,
        OpenRouterProviderConfig,
    )

    llm = LLMConfig(
        provider="linnex_llm",
        openrouter=OpenRouterProviderConfig(
            api_key="sk-main",
            api_keys=["", "YOUR_OPENROUTER_API_KEY", "sk-extra"],
            base_url="https://openrouter.ai/api/v1",
        ),
    )
    keys = resolve_provider_api_keys(llm, "openrouter")
    assert keys == ["sk-main", "sk-extra"]


def test_platform_free_candidate_order_includes_new_account_free_tier_providers():
    assert PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER == (
        "openrouter",
        "bothub",
        "groq",
        "cerebras",
        "google",
        "github",
        "huggingface",
        "nvidia",
        "mistral",
        "zai",
        "sambanova",
    )
    assert ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS == frozenset(
        {
            "groq",
            "cerebras",
            "google",
            "github",
            "huggingface",
            "nvidia",
            "mistral",
            "zai",
            "sambanova",
        }
    )


def test_llm_provider_block_covers_every_openai_compat_slug():
    from core.config.llm_openai_compat import llm_provider_block
    from core.config.models import LLMConfig

    llm = LLMConfig()
    for slug in OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER:
        block = llm_provider_block(llm, slug)
        assert block is None


def test_llm_provider_block_rejects_unknown_slug():
    from core.config.llm_openai_compat import llm_provider_block
    from core.config.models import LLMConfig

    with pytest.raises(ValueError, match="is not supported for the OpenAI-compatible API"):
        llm_provider_block(LLMConfig(), "cloudflare")


def test_placeholder_api_key_is_not_configured_for_free_pool():
    from core.config.llm_openai_compat import provider_is_configured_for_free_pool
    from core.config.models import GroqProviderConfig, LLMConfig, NvidiaProviderConfig

    llm = LLMConfig(
        groq=GroqProviderConfig(api_key="YOUR_GROQ_API_KEY"),
        nvidia=NvidiaProviderConfig(api_key="YOUR_NVIDIA_API_KEY", api_keys=["YOUR_NVIDIA_API_KEY"]),
    )
    assert provider_is_configured_for_free_pool(llm, "groq") is False
    assert provider_is_configured_for_free_pool(llm, "nvidia") is False


def test_conf_json_openai_compat_blocks_match_specs():
    import json
    from pathlib import Path

    from core.ai.providers import (
        LLM_PROVIDER_DEFAULT_BASE_URLS,
        LLM_PROVIDER_DEFAULT_MODELS_URLS,
        LLM_PROVIDER_SMOKE_MODELS,
    )

    conf_path = Path(__file__).resolve().parents[3] / "conf.json"
    payload = json.loads(conf_path.read_text(encoding="utf-8"))
    llm = payload["llm"]
    for slug in OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER:
        if slug in ("openai", "github"):
            continue
        assert slug in llm, f"conf.json llm.{slug} отсутствует"
        block = llm[slug]
        assert block["base_url"] == LLM_PROVIDER_DEFAULT_BASE_URLS[slug]
        if slug != "yandex":
            assert block["models_url"] == LLM_PROVIDER_DEFAULT_MODELS_URLS[slug]
        if slug in ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS:
            assert block["smoke_model"] == LLM_PROVIDER_SMOKE_MODELS[slug]


def test_zai_openai_compat_root_keeps_v4_suffix():
    from core.config.llm_openai_compat import (
        openai_compat_http_root,
        resolve_provider_openai_v1_base_url,
    )
    from core.config.models import LLMConfig, ZAIProviderConfig

    assert openai_compat_http_root("https://api.z.ai/api/paas/v4/") == "https://api.z.ai/api/paas/v4"
    assert openai_compat_http_root(
        "https://generativelanguage.googleapis.com/v1beta/openai"
    ) == "https://generativelanguage.googleapis.com/v1beta/openai"
    llm = LLMConfig(zai=ZAIProviderConfig(api_key="sk-zai"))
    assert resolve_provider_openai_v1_base_url(llm, "zai") == "https://api.z.ai/api/paas/v4"


def test_candidate_supports_request_vision_and_json():
    from core.ai.free_pool import PLATFORM_FREE_MODEL_SOURCE, PLATFORM_PAID_FALLBACK_SOURCE
    from core.ai.llm_config import LLMCallConfig
    from core.clients.llm.candidates import candidate_supports_request

    text_only = LLMCallConfig(
        provider="groq",
        model="text-only",
        source=PLATFORM_FREE_MODEL_SOURCE,
        input_modalities=frozenset({"text"}),
        supported_parameters=frozenset({"temperature"}),
        capability_metadata_verified=True,
    )
    vision = text_only.model_copy(
        update={"input_modalities": frozenset({"text", "image"})}
    )
    json_schema = text_only.model_copy(
        update={"supported_parameters": frozenset({"json_schema"})}
    )
    structured = text_only.model_copy(
        update={"supported_parameters": frozenset({"structured_outputs"})}
    )
    paid_fallback_text = LLMCallConfig(
        provider="openrouter",
        model="qwen/qwen-2.5-7b-instruct",
        source=PLATFORM_PAID_FALLBACK_SOURCE,
    )
    assert (
        candidate_supports_request(
            text_only, has_files=True, has_tools=False, has_response_format=False
        )
        is False
    )
    assert (
        candidate_supports_request(
            vision, has_files=True, has_tools=False, has_response_format=False
        )
        is True
    )
    assert (
        candidate_supports_request(
            paid_fallback_text,
            has_files=True,
            has_tools=False,
            has_response_format=False,
        )
        is False
    )
    assert (
        candidate_supports_request(
            paid_fallback_text,
            has_files=False,
            has_tools=False,
            has_response_format=False,
        )
        is True
    )
    assert (
        candidate_supports_request(
            text_only, has_files=False, has_tools=False, has_response_format=True
        )
        is False
    )
    assert (
        candidate_supports_request(
            json_schema, has_files=False, has_tools=False, has_response_format=True
        )
        is True
    )
    assert (
        candidate_supports_request(
            structured, has_files=False, has_tools=False, has_response_format=True
        )
        is True
    )


def test_retry_after_ttl_seconds_http_date():
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    import httpx2

    from core.clients.llm.candidate_cooldown import retry_after_ttl_seconds

    future = datetime.now(timezone.utc) + timedelta(seconds=45)
    response = httpx2.Response(
        429,
        headers={"Retry-After": format_datetime(future, usegmt=True)},
        request=httpx2.Request("POST", "https://example.test/v1/chat/completions"),
    )
    ttl = retry_after_ttl_seconds(response)
    assert 40 <= ttl <= 50


def test_retry_after_ttl_seconds_empty_header_raises():
    import httpx2

    from core.clients.llm.candidate_cooldown import retry_after_ttl_seconds

    response = httpx2.Response(
        429,
        headers={"Retry-After": "  "},
        request=httpx2.Request("POST", "https://example.test/v1/chat/completions"),
    )
    with pytest.raises(ValueError, match="Retry-After header is empty"):
        retry_after_ttl_seconds(response)
