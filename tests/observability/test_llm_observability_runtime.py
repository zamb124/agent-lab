"""Runtime tests: LLM context compile and stream TTFT logs."""

from __future__ import annotations

import pytest

from core.clients.llm.context_layer import prepare_messages_for_context_layer
from core.clients.llm.logging import log_llm_stream_response
from core.logging.attributes import (
    LOG_LLM_CONTEXT_COMPILE_MS,
    LOG_LLM_MODEL,
    LOG_LLM_PROVIDER,
    LOG_LLM_TTFT_MS,
)
from tests.fixtures.observability_log_capture import find_caplog_record, require_log_fields, require_numeric_field
from tests.observability.contracts import LLM_CONTEXT_COMPILED, LLM_STREAM_RESPONSE

pytestmark = pytest.mark.timeout(30)


@pytest.mark.asyncio
async def test_llm_context_compiled_emitted(
    observability_caplog: pytest.LogCaptureFixture,
) -> None:
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "ROLE_USER", "content": "Hello"},
    ]
    _ = await prepare_messages_for_context_layer(
        messages,
        llm_context={"budget": {"active_window_tokens": 2000}},
        metadata={"llm_provider": "mock", "llm_model": "mock-gpt-4"},
    )

    rec = find_caplog_record(
        observability_caplog,
        message=LLM_CONTEXT_COMPILED.message,
        logger_name="core.clients.llm.context_layer",
    )
    fields = require_log_fields(
        rec,
        required={
            LOG_LLM_CONTEXT_COMPILE_MS: (int, float),
        },
    )
    require_numeric_field(fields, LOG_LLM_CONTEXT_COMPILE_MS, min_value=0.0)


def test_llm_stream_response_includes_ttft(
    observability_caplog: pytest.LogCaptureFixture,
) -> None:
    log_llm_stream_response(
        url="http://mock/llm",
        content="hello",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        provider="mock",
        model="mock-gpt-4",
        duration_ms=120.0,
        ttft_ms=45.0,
    )

    rec = find_caplog_record(
        observability_caplog,
        message=LLM_STREAM_RESPONSE.message,
        logger_name="core.clients.llm.logging",
    )
    fields = require_log_fields(
        rec,
        required={
            LOG_LLM_PROVIDER: str,
            LOG_LLM_MODEL: str,
            LOG_LLM_TTFT_MS: (int, float),
        },
    )
    assert fields[LOG_LLM_PROVIDER] == "mock"
    assert fields[LOG_LLM_MODEL] == "mock-gpt-4"
    require_numeric_field(fields, LOG_LLM_TTFT_MS, min_value=0.0)
