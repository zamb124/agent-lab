"""Gate: OpenRouter OpenAPI fixture exists and Chat schemas resolve."""

from __future__ import annotations

from tests.agent.contract.openrouter_schemas import (
    get_openrouter_schema,
    load_openrouter_openapi,
    openrouter_openapi_fixture_path,
    validate_against_openrouter_schema,
)


def test_openrouter_openapi_fixture_exists() -> None:
    path = openrouter_openapi_fixture_path()
    assert path.is_file()
    assert path.stat().st_size > 100_000


def test_openrouter_openapi_loads_and_lists_chat_paths() -> None:
    openapi = load_openrouter_openapi()
    assert openapi.get("openapi", "").startswith("3.")
    paths = openapi.get("paths")
    assert isinstance(paths, dict)
    assert "/chat/completions" in paths
    assert "/models" in paths


def test_openrouter_chat_schemas_resolve() -> None:
    for schema_name in (
        "ChatRequest",
        "ChatResult",
        "ChatStreamChunk",
        "ChatUsage",
        "ChatChoice",
    ):
        schema = get_openrouter_schema(schema_name)
        assert isinstance(schema, dict)
        assert "properties" in schema or "$ref" not in schema


def test_minimal_chat_result_validates_against_openrouter_schema() -> None:
    payload = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": "auto",
        "system_fingerprint": None,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "hi"},
            }
        ],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        },
    }
    validate_against_openrouter_schema("ChatResult", payload)
