"""OpenRouter free model cache filtering/ranking."""

import json

from core.clients.llm.openrouter_free_models import (
    is_free_text_model,
    parse_openrouter_free_models,
    rank_openrouter_free_models,
    serialize_openrouter_free_models,
)
from core.types import JsonObject, parse_json_object


def test_rank_openrouter_free_models_prefers_larger_models_and_keeps_router_last() -> None:
    records = rank_openrouter_free_models(
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
        include_router_as_last=True,
    )

    assert [record.id for record in records] == [
        "large/model-120b:free",
        "small/model-8b:free",
        "openrouter/free",
    ]


def test_is_free_text_model_rejects_paid_expired_or_non_text_models() -> None:
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

    assert is_free_text_model(base)
    assert is_free_text_model({**base, "pricing": {"prompt": "0", "completion": "0"}})
    assert not is_free_text_model({**base, "pricing": {"prompt": "0.01"}})
    assert not is_free_text_model(
        {**base, "pricing": {"prompt": "0", "completion": "0", "request": "0.01"}}
    )
    assert not is_free_text_model({**base, "expiration_date": 1_800_000_000})
    assert not is_free_text_model(
        {
            **base,
            "architecture": {
                "input_modalities": ["image"],
                "output_modalities": ["text"],
            },
        }
    )


def test_free_model_cache_roundtrips_capability_metadata() -> None:
    records = rank_openrouter_free_models(
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
        include_router_as_last=True,
    )

    parsed = parse_openrouter_free_models(serialize_openrouter_free_models(records))

    assert len(parsed) == 1
    assert parsed[0].id == "vendor/model-70B:free"
    assert parsed[0].score == 70
    assert parsed[0].context_length == 131072
    assert parsed[0].supported_parameters == ("response_format", "tools")
    assert parsed[0].input_modalities == ("image", "text")
    assert parsed[0].output_modalities == ("text",)
    assert parsed[0].created == 42


def test_parse_openrouter_free_models_treats_bad_cache_as_empty() -> None:
    assert parse_openrouter_free_models(None) == []
    assert parse_openrouter_free_models("{bad-json") == []
    assert parse_openrouter_free_models('{"version":999,"models":[]}') == []
    assert parse_openrouter_free_models('{"version":1,"models":"bad"}') == []
