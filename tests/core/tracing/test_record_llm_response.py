"""record_llm_response: кастомный billing_resource_name."""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from opentelemetry.sdk.trace import Span as SDKSpan

import core.tracing.attributes as attr
from core.tracing.provider import ensure_tracer_provider
from core.tracing.tracer import PlatformTracer, _llm_operation_name
from core.types import OtelAttributeValue


@contextmanager
def sdk_span(attributes: dict[str, OtelAttributeValue] | None = None) -> Iterator[SDKSpan]:
    otel_tracer = ensure_tracer_provider("test").get_tracer("test")
    with otel_tracer.start_as_current_span(
        "test.llm",
        attributes=attributes,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        assert isinstance(span, SDKSpan)
        yield span


def span_attr(span: SDKSpan, key: str) -> OtelAttributeValue | None:
    span_attrs = span.attributes
    assert span_attrs is not None
    return span_attrs.get(key)


@pytest.fixture
def tracer() -> PlatformTracer:
    return PlatformTracer(service_name="test")


def test_record_llm_response_default_billing_uses_model(tracer: PlatformTracer) -> None:
    with sdk_span({attr.ATTR_LLM_MODEL: "my-model"}) as span:
        tracer.record_llm_response(span, 1, 2, False, 1.0)

        assert span_attr(span, attr.ATTR_BILLING_RESOURCE_NAME) == "llm:my-model"


def test_record_llm_response_billing_resource_name_override(tracer: PlatformTracer) -> None:
    with sdk_span({attr.ATTR_LLM_MODEL: "ignored"}) as span:
        tracer.record_llm_response(
            span, 1, 2, False, 1.0, billing_resource_name="llm:byok"
        )

        assert span_attr(span, attr.ATTR_BILLING_RESOURCE_NAME) == "llm:byok"


def test_record_llm_response_updates_span_model_and_source(tracer: PlatformTracer) -> None:
    with sdk_span({attr.ATTR_LLM_MODEL: "auto"}) as span:
        tracer.record_llm_response(
            span,
            10,
            5,
            False,
            1.0,
            llm_provider="openrouter",
            llm_model="qwen/qwen3-coder:free",
            candidate_source="platform_free",
        )

        assert span_attr(span, attr.ATTR_LLM_MODEL) == "qwen/qwen3-coder:free"
        assert span_attr(span, attr.ATTR_LLM_PROVIDER) == "openrouter"
        assert span_attr(span, attr.ATTR_LLM_CANDIDATE_SOURCE) == "platform_free"
        assert (
            span_attr(span, attr.ATTR_BILLING_RESOURCE_NAME)
            == "llm:qwen/qwen3-coder:free"
        )


def test_record_llm_response_writes_context_layer_observability(tracer: PlatformTracer) -> None:
    with sdk_span({attr.ATTR_LLM_MODEL: "model"}) as span:
        tracer.record_llm_response(
            span,
            10,
            5,
            False,
            1.0,
            llm_context={
                "usage": {
                    "max_input_tokens": 32,
                    "model_context_length": 32,
                    "total_input_tokens": 18,
                },
                "selected_blocks": [{"kind": "memory", "stable_key": "m1"}],
                "dropped_blocks": [{"kind": "rag", "stable_key": "r1"}],
            },
        )

        assert span_attr(span, attr.ATTR_LLM_CONTEXT_ENABLED) is True
        assert span_attr(span, attr.ATTR_LLM_CONTEXT_MAX_INPUT_TOKENS) == 32
        assert span_attr(span, attr.ATTR_LLM_CONTEXT_MODEL_CONTEXT_LENGTH) == 32
        assert span_attr(span, attr.ATTR_LLM_CONTEXT_TOTAL_INPUT_TOKENS) == 18
        assert span_attr(span, attr.ATTR_LLM_CONTEXT_SELECTED_BLOCKS_COUNT) == 1
        assert span_attr(span, attr.ATTR_LLM_CONTEXT_DROPPED_BLOCKS_COUNT) == 1
        context = span_attr(span, attr.ATTR_LLM_CONTEXT)
        assert isinstance(context, str)
        assert '"stable_key": "m1"' in context


def test_llm_operation_name_uses_resolved_span_model() -> None:
    with sdk_span({attr.ATTR_LLM_MODEL: "qwen/qwen3-coder:free"}) as span:
        assert _llm_operation_name(span, "auto") == "llm.qwen/qwen3-coder:free"
