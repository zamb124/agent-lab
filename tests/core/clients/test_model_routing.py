"""Контракт split_provider_prefixed_model (префикс платформенного провайдера в model)."""

import pytest
from pydantic import ValidationError

from core.ai.company_settings import PLATFORM_LLM_PROVIDERS
from core.ai.providers import (
    ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS,
    HUMANITEC_LLM_PROVIDER,
    LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER,
    OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
    PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER,
    PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS,
    PLATFORM_LLM_PROVIDER_ORDER,
    ZERO_PRICE_LLM_PROVIDER_SLUGS,
    humanitec_llms_model_ref,
    split_humanitec_llms_model_ref,
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


def test_humanitec_llms_model_ref_is_provider_prefixed_free_pool_model():
    assert (
        humanitec_llms_model_ref("openrouter", "qwen/qwen3-coder:free")
        == "openrouter:qwen/qwen3-coder:free"
    )
    assert split_humanitec_llms_model_ref("openrouter:qwen/qwen3-coder:free") == (
        "openrouter",
        "qwen/qwen3-coder:free",
    )
    assert split_humanitec_llms_model_ref("auto") is None
    assert split_humanitec_llms_model_ref("deepinfra:deepseek-ai/DeepSeek-V3") is None


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
        HUMANITEC_LLM_PROVIDER,
        *OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
    )
    assert PLATFORM_LLM_PROVIDERS == PLATFORM_LLM_PROVIDER_ORDER


def test_free_model_policy_is_explicit_for_every_provider():
    assert tuple(LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER) == OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER
    assert LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER["openrouter"] == "zero_price_catalog"
    assert LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER["bothub"] == "zero_price_catalog"
    assert LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER["groq"] == "account_free_tier"
    assert PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS == (
        ZERO_PRICE_LLM_PROVIDER_SLUGS | ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS
    )
