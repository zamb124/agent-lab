"""Provider-neutral free model catalog: filtering, ranking and cache."""

import json
from types import SimpleNamespace

from core.clients.llm.model_routing import OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER
from core.clients.llm.platform_free_models import (
    BotHubFreeModelAdapter,
    ConfiguredAccountFreeTierModelAdapter,
    OpenRouterPlatformFreeModelAdapter,
    PlatformFreeModelRecord,
    apply_platform_model_score_overrides,
    humanitec_llms_model_options_from_records,
    is_bothub_free_text_model,
    is_openrouter_verified_free_text_model,
    parse_platform_free_models,
    platform_free_model_policy_for_provider,
    serialize_platform_free_models,
    sort_platform_free_records,
)
from core.types import JsonObject, parse_json_object


def test_openrouter_adapter_prefers_larger_models_and_keeps_router_last() -> None:
    records = OpenRouterPlatformFreeModelAdapter().records_from_items(
        [
            {
                "id": "small/model-8b:free",
                "name": "Small 8B",
                "pricing": {"prompt": "0", "completion": "0", "request": "0"},
                "architecture": {
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                },
                "context_length": 32768,
                "supported_parameters": ["temperature"],
                "created": 1,
            },
            {
                "id": "large/model-120b:free",
                "name": "Large 120B",
                "pricing": {"prompt": "0", "completion": "0", "request": "0"},
                "architecture": {
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                },
                "context_length": 8192,
                "supported_parameters": ["response_format"],
                "created": 1,
            },
            {
                "id": "paid/model-405b",
                "name": "Paid 405B",
                "pricing": {"prompt": "0.1", "completion": "0", "request": "0"},
                "architecture": {
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                },
            },
            {
                "id": "openrouter/free",
                "name": "Free Router",
                "pricing": {"prompt": "0", "completion": "0", "request": "0"},
                "architecture": {
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                },
            },
        ],
        max_candidates=10,
        include_provider_router_as_last=True,
    )

    assert [(record.provider, record.id) for record in records] == [
        ("openrouter", "large/model-120b:free"),
        ("openrouter", "small/model-8b:free"),
        ("openrouter", "openrouter/free"),
    ]


def test_openrouter_verified_free_filter_rejects_paid_expired_or_non_text_models() -> None:
    base: JsonObject = parse_json_object(
        json.dumps(
            {
                "id": "vendor/model-80b:free",
                "pricing": {"prompt": "0", "completion": "0", "request": "0"},
                "architecture": {
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                },
                "expiration_date": None,
            }
        )
    )

    assert is_openrouter_verified_free_text_model(base)
    assert is_openrouter_verified_free_text_model({**base, "pricing": {"prompt": "0", "completion": "0"}})
    assert not is_openrouter_verified_free_text_model({**base, "pricing": {"prompt": "0.01"}})
    assert not is_openrouter_verified_free_text_model(
        {**base, "pricing": {"prompt": "0", "completion": "0", "request": "0.01"}}
    )
    assert not is_openrouter_verified_free_text_model({**base, "expiration_date": 1_800_000_000})
    assert not is_openrouter_verified_free_text_model(
        {
            **base,
            "architecture": {
                "input_modalities": ["image"],
                "output_modalities": ["text"],
            },
        }
    )


def test_bothub_adapter_maps_free_text_features_to_platform_capabilities() -> None:
    records = BotHubFreeModelAdapter().records_from_items(
        [
            {
                "id": "llama-3.3-70b-instruct:free",
                "label": "llama-3.3-70B Instruct Free",
                "pricing": {"input": 0, "output": 0, "request": 0},
                "contextLength": 131072,
                "maxTokens": 8192,
                "features": ["TEXT_TO_TEXT", "DOCUMENT_TO_TEXT", "TOOLS"],
                "disabled": False,
                "disabledApi": False,
                "deletedAt": None,
                "allowedPlanType": None,
            },
            {
                "id": "paid-model",
                "pricing": {"input": 0.1, "output": 0, "request": 0},
                "features": ["TEXT_TO_TEXT"],
            },
        ],
        max_candidates=10,
        include_provider_router_as_last=True,
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


def test_bothub_free_filter_rejects_plan_gated_unavailable_models() -> None:
    base: JsonObject = parse_json_object(
        json.dumps(
            {
                "id": "model:free",
                "pricing": {"input": 0, "output": 0, "request": 0},
                "features": ["TEXT_TO_TEXT"],
                "disabled": False,
                "disabledApi": False,
                "deletedAt": None,
                "allowedPlanType": None,
            }
        )
    )

    assert is_bothub_free_text_model(base)
    assert not is_bothub_free_text_model({**base, "pricing": {"input": 0, "output": 1}})
    assert not is_bothub_free_text_model({**base, "features": ["IMAGE_TO_TEXT"]})
    assert not is_bothub_free_text_model({**base, "disabledApi": True})
    assert not is_bothub_free_text_model(
        {**base, "allowedPlanType": "ELITE", "isAllowed": False}
    )
    assert is_bothub_free_text_model(
        {**base, "allowedPlanType": "ELITE", "isAllowed": True}
    )


def test_platform_free_model_cache_roundtrips_provider_and_capability_metadata() -> None:
    records = OpenRouterPlatformFreeModelAdapter().records_from_items(
        [
            {
                "id": "vendor/model-70B:free",
                "name": "Vendor 70B",
                "pricing": {"prompt": "0", "completion": "0", "request": "0"},
                "architecture": {
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["text"],
                },
                "context_length": 131072,
                "supported_parameters": ["tools", "response_format"],
                "created": 42,
            }
        ],
        max_candidates=10,
        include_provider_router_as_last=True,
    )

    parsed = parse_platform_free_models(serialize_platform_free_models(records))

    assert len(parsed) == 1
    assert parsed[0].provider == "openrouter"
    assert parsed[0].id == "vendor/model-70B:free"
    assert parsed[0].score == 70
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


def test_platform_model_score_overrides_replace_heuristic_score() -> None:
    records = apply_platform_model_score_overrides(
        [
            PlatformFreeModelRecord(
                provider="github",
                id="openai/gpt-4o-mini",
                score=0,
                context_length=None,
                supported_parameters=(),
                input_modalities=("text",),
                output_modalities=("text",),
                free_reason="account_free_tier",
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
        ],
        {("github", "openai/gpt-4o-mini"): 82},
    )

    assert [(record.provider, record.id, record.score) for record in records] == [
        ("github", "openai/gpt-4o-mini", 82),
        ("groq", "llama-3.1-8b-instant", 8),
    ]


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


def test_parse_platform_free_models_treats_bad_cache_as_empty() -> None:
    assert parse_platform_free_models(None) == []
    assert parse_platform_free_models("{bad-json") == []
    assert parse_platform_free_models('{"version":999,"models":[]}') == []
    assert parse_platform_free_models('{"version":1,"models":"bad"}') == []


def test_every_platform_provider_has_explicit_free_model_policy() -> None:
    policies = {
        provider: platform_free_model_policy_for_provider(provider)
        for provider in OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER
    }

    assert set(policies) == set(OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER)
    assert all(policy != "unknown_provider" for policy in policies.values())


def test_account_free_tier_adapter_publishes_smoke_model_as_text_only_candidate() -> None:
    adapter = ConfiguredAccountFreeTierModelAdapter("groq")
    records = adapter.records_from_items(
        [{"id": "llama-3.1-8b-instant", "name": "llama-3.1-8b-instant"}],
        max_candidates=10,
        include_provider_router_as_last=True,
    )

    assert len(records) == 1
    record = records[0]
    assert record.provider == "groq"
    assert record.id == "llama-3.1-8b-instant"
    assert record.free_reason == "account_free_tier"
    assert record.input_modalities == ("text",)
    assert record.output_modalities == ("text",)
    assert record.supported_parameters == ()


async def test_account_free_tier_adapter_reads_configured_smoke_model() -> None:
    adapter = ConfiguredAccountFreeTierModelAdapter("google")
    settings = SimpleNamespace(
        llm=SimpleNamespace(
            google=SimpleNamespace(
                api_key="test-key",
                smoke_model="gemini-2.5-flash-lite",
            )
        )
    )

    assert adapter.is_configured(settings)
    assert await adapter.fetch_model_items(settings) == [
        {"id": "gemini-2.5-flash-lite", "name": "gemini-2.5-flash-lite"}
    ]
