"""record_llm_response: кастомный billing_resource_name."""

import pytest

import core.tracing.attributes as attr
from core.tracing.tracer import PlatformTracer, _llm_operation_name


class SpanProbe:
    def __init__(self, attributes: dict | None = None) -> None:
        self.attributes = attributes or {}
        self.payloads: list[dict] = []
        self.attribute_calls: list[tuple[str, object]] = []

    def set_attributes(self, attributes: dict) -> None:
        self.payloads.append(dict(attributes))
        self.attributes.update(attributes)

    def set_attribute(self, key: str, value: object) -> None:
        self.attribute_calls.append((key, value))
        self.attributes[key] = value


@pytest.fixture
def tracer() -> PlatformTracer:
    return PlatformTracer(service_name="test")


def test_record_llm_response_default_billing_uses_model(tracer: PlatformTracer) -> None:
    span = SpanProbe({attr.ATTR_LLM_MODEL: "my-model"})

    tracer.record_llm_response(span, 1, 2, False, 1.0)
    billing = span.payloads[-1]
    assert billing[attr.ATTR_BILLING_RESOURCE_NAME] == "llm:my-model"


def test_record_llm_response_billing_resource_name_override(tracer: PlatformTracer) -> None:
    span = SpanProbe({attr.ATTR_LLM_MODEL: "ignored"})

    tracer.record_llm_response(
        span, 1, 2, False, 1.0, billing_resource_name="llm:byok"
    )
    billing = span.payloads[-1]
    assert billing[attr.ATTR_BILLING_RESOURCE_NAME] == "llm:byok"


def test_record_llm_response_updates_span_model_and_source(tracer: PlatformTracer) -> None:
    span = SpanProbe({attr.ATTR_LLM_MODEL: "auto"})

    tracer.record_llm_response(
        span,
        10,
        5,
        False,
        1.0,
        llm_provider="openrouter",
        llm_model="qwen/qwen3-coder:free",
        candidate_source="openrouter_free",
    )

    assert (attr.ATTR_LLM_MODEL, "qwen/qwen3-coder:free") in span.attribute_calls
    assert (attr.ATTR_LLM_PROVIDER, "openrouter") in span.attribute_calls
    assert (attr.ATTR_LLM_CANDIDATE_SOURCE, "openrouter_free") in span.attribute_calls
    billing = span.payloads[-1]
    assert billing[attr.ATTR_BILLING_RESOURCE_NAME] == "llm:qwen/qwen3-coder:free"


def test_record_llm_response_writes_context_layer_observability(tracer: PlatformTracer) -> None:
    span = SpanProbe({attr.ATTR_LLM_MODEL: "model"})

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

    assert span.attributes[attr.ATTR_LLM_CONTEXT_ENABLED] is True
    assert span.attributes[attr.ATTR_LLM_CONTEXT_MAX_INPUT_TOKENS] == 32
    assert span.attributes[attr.ATTR_LLM_CONTEXT_MODEL_CONTEXT_LENGTH] == 32
    assert span.attributes[attr.ATTR_LLM_CONTEXT_TOTAL_INPUT_TOKENS] == 18
    assert span.attributes[attr.ATTR_LLM_CONTEXT_SELECTED_BLOCKS_COUNT] == 1
    assert span.attributes[attr.ATTR_LLM_CONTEXT_DROPPED_BLOCKS_COUNT] == 1
    assert '"stable_key": "m1"' in span.attributes[attr.ATTR_LLM_CONTEXT]


def test_llm_operation_name_uses_resolved_span_model() -> None:
    span = SpanProbe({attr.ATTR_LLM_MODEL: "qwen/qwen3-coder:free"})

    assert _llm_operation_name(span, "auto") == "llm.qwen/qwen3-coder:free"
