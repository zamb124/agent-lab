"""record_llm_response: кастомный billing_resource_name."""

from unittest.mock import MagicMock

import pytest

import core.tracing.attributes as attr
from core.tracing.tracer import PlatformTracer, _llm_operation_name


@pytest.fixture
def tracer() -> PlatformTracer:
    return PlatformTracer(service_name="test")


def test_record_llm_response_default_billing_uses_model(tracer: PlatformTracer) -> None:
    span = MagicMock()
    span.attributes = {attr.ATTR_LLM_MODEL: "my-model"}
    payloads: list[dict] = []

    def _capture(d: dict) -> None:
        payloads.append(dict(d))

    span.set_attributes = MagicMock(side_effect=_capture)
    span.set_attribute = MagicMock()
    tracer.record_llm_response(span, 1, 2, False, 1.0)
    billing = payloads[-1]
    assert billing[attr.ATTR_BILLING_RESOURCE_NAME] == "llm:my-model"


def test_record_llm_response_billing_resource_name_override(tracer: PlatformTracer) -> None:
    span = MagicMock()
    span.attributes = {attr.ATTR_LLM_MODEL: "ignored"}
    payloads: list[dict] = []

    def _capture(d: dict) -> None:
        payloads.append(dict(d))

    span.set_attributes = MagicMock(side_effect=_capture)
    span.set_attribute = MagicMock()
    tracer.record_llm_response(
        span, 1, 2, False, 1.0, billing_resource_name="llm:byok"
    )
    billing = payloads[-1]
    assert billing[attr.ATTR_BILLING_RESOURCE_NAME] == "llm:byok"


def test_record_llm_response_updates_span_model_and_source(tracer: PlatformTracer) -> None:
    span = MagicMock()
    span.attributes = {attr.ATTR_LLM_MODEL: "auto"}
    payloads: list[dict] = []

    def _capture(d: dict) -> None:
        payloads.append(dict(d))

    span.set_attributes = MagicMock(side_effect=_capture)
    span.set_attribute = MagicMock()

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

    span.set_attribute.assert_any_call(attr.ATTR_LLM_MODEL, "qwen/qwen3-coder:free")
    span.set_attribute.assert_any_call(attr.ATTR_LLM_PROVIDER, "openrouter")
    span.set_attribute.assert_any_call(attr.ATTR_LLM_CANDIDATE_SOURCE, "openrouter_free")
    billing = payloads[-1]
    assert billing[attr.ATTR_BILLING_RESOURCE_NAME] == "llm:qwen/qwen3-coder:free"


def test_llm_operation_name_uses_resolved_span_model() -> None:
    span = MagicMock()
    span.attributes = {attr.ATTR_LLM_MODEL: "qwen/qwen3-coder:free"}

    assert _llm_operation_name(span, "auto") == "llm.qwen/qwen3-coder:free"
