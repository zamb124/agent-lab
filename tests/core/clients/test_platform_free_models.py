"""Provider-neutral free model catalog: filtering, ranking and cache."""

from types import SimpleNamespace
from typing import cast

import pytest

from core.ai.free_pool import (
    PlatformFreeModelRecord,
    compute_platform_free_record_scores,
    humanitec_llms_model_options_from_records,
    parse_platform_free_models,
    platform_free_model_policy_for_provider,
    platform_free_records_from_model_records,
    serialize_platform_free_models,
    sort_platform_free_records,
)
from core.ai.models import AIModelRecord, ArtificialAnalysisIndices
from core.ai.providers import OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER, AICapability
from core.ai.scoring import PlatformModelScoreOverlay
from core.config.base import BaseSettings


def _settings_stub() -> BaseSettings:
    return cast(
        BaseSettings,
        SimpleNamespace(
            llm=SimpleNamespace(
                groq=SimpleNamespace(api_key="test-key", smoke_model="llama-3.1-8b-instant"),
                google=SimpleNamespace(api_key="test-key", smoke_model="gemini-2.5-flash-lite"),
                github=SimpleNamespace(api_key="test-key", smoke_model="openai/gpt-4o-mini"),
                huggingface=SimpleNamespace(api_key="test-key", smoke_model="meta-llama/Llama-3.1-8B-Instruct"),
            )
        ),
    )


def test_catalog_free_records_prefers_larger_models_and_keeps_router_last_by_score() -> None:
    catalog = [
        AIModelRecord(
            provider="openrouter",
            model_id="small/model-8b:free",
            capabilities=(AICapability.LLM_CHAT,),
            input_modalities=("text",),
            output_modalities=("text",),
            context_length=32768,
            supported_parameters=("temperature",),
            created=1,
            is_free=True,
            free_reason="zero_price_catalog",
            raw={"name": "Small 8B"},
        ),
        AIModelRecord(
            provider="openrouter",
            model_id="large/model-120b:free",
            capabilities=(AICapability.LLM_CHAT,),
            input_modalities=("text",),
            output_modalities=("text",),
            context_length=8192,
            supported_parameters=("response_format",),
            created=1,
            is_free=True,
            free_reason="zero_price_catalog",
            raw={"name": "Large 120B"},
        ),
        AIModelRecord(
            provider="openrouter",
            model_id="paid/model-405b",
            capabilities=(AICapability.LLM_CHAT,),
            input_modalities=("text",),
            output_modalities=("text",),
            is_free=False,
        ),
        AIModelRecord(
            provider="openrouter",
            model_id="openrouter/free",
            capabilities=(AICapability.LLM_CHAT,),
            input_modalities=("text",),
            output_modalities=("text",),
            is_free=True,
            free_reason="zero_price_catalog",
            raw={"name": "Free Router"},
        ),
    ]
    records = sort_platform_free_records(
        compute_platform_free_record_scores(
            platform_free_records_from_model_records(catalog, settings=_settings_stub()),
            catalog_records=catalog,
            overlays=None,
        ),
        max_candidates=10,
    )

    assert [(record.provider, record.id, record.free_reason) for record in records] == [
        ("openrouter", "large/model-120b:free", "verified_zero_price"),
        ("openrouter", "small/model-8b:free", "verified_zero_price"),
        ("openrouter", "openrouter/free", "verified_zero_price"),
    ]


def test_catalog_free_records_reject_paid_non_text_or_non_chat_models() -> None:
    records = platform_free_records_from_model_records(
        [
            AIModelRecord(
                provider="openrouter",
                model_id="vendor/model-80b:free",
                capabilities=(AICapability.LLM_CHAT,),
                input_modalities=("text",),
                output_modalities=("text",),
                is_free=True,
            ),
            AIModelRecord(
                provider="openrouter",
                model_id="paid/model",
                capabilities=(AICapability.LLM_CHAT,),
                input_modalities=("text",),
                output_modalities=("text",),
                is_free=False,
            ),
            AIModelRecord(
                provider="openrouter",
                model_id="vision-only-free",
                capabilities=(AICapability.LLM_CHAT,),
                input_modalities=("image",),
                output_modalities=("text",),
                is_free=True,
            ),
            AIModelRecord(
                provider="openrouter",
                model_id="embedding-free",
                capabilities=(AICapability.EMBEDDING,),
                input_modalities=("text",),
                output_modalities=("embeddings",),
                is_free=True,
            ),
        ],
        settings=_settings_stub(),
    )

    assert [(record.provider, record.id) for record in records] == [
        ("openrouter", "vendor/model-80b:free")
    ]


def test_catalog_bothub_record_preserves_capability_metadata_from_adapter_sync() -> None:
    records = platform_free_records_from_model_records(
        [
            AIModelRecord(
                provider="bothub",
                model_id="llama-3.3-70b-instruct:free",
                capabilities=(AICapability.LLM_CHAT,),
                input_modalities=("file", "text"),
                output_modalities=("text",),
                supported_parameters=("tool_choice", "tools"),
                context_length=131072,
                is_free=True,
                free_reason="zero_price_catalog",
                raw={"label": "llama-3.3-70B Instruct Free", "maxTokens": 8192},
            )
        ],
        settings=_settings_stub(),
    )

    assert len(records) == 1
    record = records[0]
    assert record.provider == "bothub"
    assert record.id == "llama-3.3-70b-instruct:free"
    assert record.context_length == 131072
    assert record.max_tokens == 8192
    assert record.supported_parameters == ("tool_choice", "tools")
    assert record.input_modalities == ("file", "text")
    assert record.output_modalities == ("text",)


def test_platform_free_model_cache_roundtrips_provider_and_capability_metadata() -> None:
    records = platform_free_records_from_model_records(
        [
            AIModelRecord(
                provider="openrouter",
                model_id="vendor/model-70B:free",
                capabilities=(AICapability.LLM_CHAT,),
                input_modalities=("image", "text"),
                output_modalities=("text",),
                context_length=131072,
                supported_parameters=("response_format", "tools"),
                created=42,
                is_free=True,
                free_reason="zero_price_catalog",
                raw={"name": "Vendor 70B"},
            )
        ],
        settings=_settings_stub(),
    )

    parsed = parse_platform_free_models(serialize_platform_free_models(records))

    assert len(parsed) == 1
    assert parsed[0].provider == "openrouter"
    assert parsed[0].id == "vendor/model-70B:free"
    assert parsed[0].score == 0.0
    assert parsed[0].context_length == 131072
    assert parsed[0].supported_parameters == ("response_format", "tools")
    assert parsed[0].input_modalities == ("image", "text")
    assert parsed[0].output_modalities == ("text",)
    assert parsed[0].created == 42


def test_platform_free_model_sort_is_power_first_then_capabilities_then_confidence() -> None:
    records = sort_platform_free_records(
        [
            PlatformFreeModelRecord(
                provider="openrouter",
                id="verified-unknown",
                score=0,
                context_length=1_048_576,
                supported_parameters=("tools",),
                input_modalities=("text",),
                output_modalities=("text",),
                free_reason="verified_zero_price",
            ),
            PlatformFreeModelRecord(
                provider="groq",
                id="llama-3.1-8b-instant",
                score=8,
                context_length=None,
                supported_parameters=(),
                input_modalities=("text",),
                output_modalities=("text",),
                free_reason="account_free_tier",
            ),
            PlatformFreeModelRecord(
                provider="bothub",
                id="verified-8b",
                score=8,
                context_length=4096,
                supported_parameters=(),
                input_modalities=("text",),
                output_modalities=("text",),
                free_reason="verified_zero_price",
            ),
        ],
        max_candidates=10,
    )

    assert [(record.provider, record.id) for record in records] == [
        ("bothub", "verified-8b"),
        ("groq", "llama-3.1-8b-instant"),
        ("openrouter", "verified-unknown"),
    ]


def test_compute_platform_free_record_scores_uses_aa_and_overlay() -> None:
    catalog_record = AIModelRecord(
        provider="openrouter",
        model_id="tencent/hy3:free",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
        context_length=262144,
        supported_parameters=("tools",),
        is_free=True,
        free_reason="zero_price_catalog",
        raw={"name": "Hy3 295B"},
        artificial_analysis=ArtificialAnalysisIndices(
            intelligence_index=71.0,
            model_permaslug="tencent/hy3",
        ),
    )
    records = compute_platform_free_record_scores(
        platform_free_records_from_model_records([catalog_record], settings=_settings_stub()),
        catalog_records=[catalog_record],
        overlays={
            ("openrouter", "tencent/hy3:free"): PlatformModelScoreOverlay(
                editorial_prior=1.0,
                enabled=True,
                note=None,
            )
        },
    )
    assert len(records) == 1
    assert records[0].score == 72.0


def test_compute_platform_free_record_scores_skips_disabled_overlay() -> None:
    catalog_record = AIModelRecord(
        provider="openrouter",
        model_id="vendor/disabled:free",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
        is_free=True,
    )
    records = compute_platform_free_record_scores(
        platform_free_records_from_model_records([catalog_record], settings=_settings_stub()),
        catalog_records=[catalog_record],
        overlays={
            ("openrouter", "vendor/disabled:free"): PlatformModelScoreOverlay(
                editorial_prior=0.0,
                enabled=False,
                note=None,
            )
        },
    )
    assert records == []


def test_compute_platform_free_record_scores_requires_catalog() -> None:
    with pytest.raises(ValueError, match="отсутствует в каталоге"):
        compute_platform_free_record_scores(
            [
                PlatformFreeModelRecord(
                    provider="openrouter",
                    id="missing:free",
                    score=0.0,
                    context_length=None,
                    supported_parameters=(),
                    input_modalities=("text",),
                    output_modalities=("text",),
                )
            ],
            catalog_records=[],
            overlays=None,
        )


def test_humanitec_llms_model_options_are_auto_plus_provider_prefixed_free_models() -> None:
    options = humanitec_llms_model_options_from_records(
        [
            PlatformFreeModelRecord(
                provider="openrouter",
                id="qwen/qwen3-coder:free",
                score=96,
                context_length=262144,
                max_tokens=8192,
                supported_parameters=("tools", "response_format"),
                input_modalities=("text",),
                output_modalities=("text",),
            ),
            PlatformFreeModelRecord(
                provider="groq",
                id="llama-3.1-8b-instant",
                score=8,
                context_length=None,
                max_tokens=None,
                supported_parameters=(),
                input_modalities=("text",),
                output_modalities=("text",),
                free_reason="account_free_tier",
            ),
        ]
    )

    assert options[0] == {"value": "auto", "label": "auto", "kind": "auto"}
    assert options[1]["value"] == "openrouter:qwen/qwen3-coder:free"
    assert options[1]["provider"] == "openrouter"
    assert options[1]["model_id"] == "qwen/qwen3-coder:free"
    assert options[1]["supported_parameters"] == ["tools", "response_format"]
    assert options[2]["value"] == "groq:llama-3.1-8b-instant"
    assert options[2]["free_reason"] == "account_free_tier"


def test_parse_platform_free_models_empty_cache_is_empty() -> None:
    assert parse_platform_free_models(None) == []


def test_parse_platform_free_models_rejects_corrupt_cache() -> None:
    with pytest.raises(ValueError):
        parse_platform_free_models("{bad-json")
    with pytest.raises(ValueError):
        parse_platform_free_models('{"version":999,"models":[]}')
    with pytest.raises(ValueError):
        parse_platform_free_models('{"version":1,"models":"bad"}')


def test_every_platform_provider_has_explicit_free_model_policy() -> None:
    policies = {
        provider: platform_free_model_policy_for_provider(provider)
        for provider in OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER
    }

    assert set(policies) == set(OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER)


def test_account_free_tier_includes_all_text_chat_catalog_models() -> None:
    records = platform_free_records_from_model_records(
        [
            AIModelRecord(
                provider="groq",
                model_id="llama-3.1-8b-instant",
                capabilities=(AICapability.LLM_CHAT,),
                input_modalities=("text",),
                output_modalities=("text",),
                context_length=131072,
                supported_parameters=("tools",),
                raw={"name": "llama-3.1-8b-instant"},
            ),
            AIModelRecord(
                provider="groq",
                model_id="other-free-tier-model",
                capabilities=(AICapability.LLM_CHAT,),
                input_modalities=("text",),
                output_modalities=("text",),
            ),
        ],
        settings=_settings_stub(),
    )

    assert {(record.provider, record.id) for record in records} == {
        ("groq", "llama-3.1-8b-instant"),
        ("groq", "other-free-tier-model"),
    }
    assert all(record.free_reason == "account_free_tier" for record in records)


def test_account_free_tier_includes_non_smoke_google_text_chat() -> None:
    records = platform_free_records_from_model_records(
        [
            AIModelRecord(
                provider="google",
                model_id="gemini-2.5-pro",
                capabilities=(AICapability.LLM_CHAT,),
                input_modalities=("text",),
                output_modalities=("text",),
            )
        ],
        settings=_settings_stub(),
    )

    assert len(records) == 1
    assert records[0].id == "gemini-2.5-pro"
    assert records[0].free_reason == "account_free_tier"
