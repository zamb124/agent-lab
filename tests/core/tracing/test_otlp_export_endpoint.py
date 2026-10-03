"""OTLP endpoint берётся из Settings, не из OTEL_EXPORTER_OTLP_ENDPOINT."""

import pytest

from core.config.base import BaseSettings
from core.config.models import TracingConfig
from core.tracing.provider import _otlp_export_endpoint


def test_otlp_export_endpoint_prefers_explicit_value() -> None:
    config = TracingConfig(
        otlp_endpoint="http://alloy:4317",
        tempo_enabled=True,
        tempo_endpoint="http://localhost:4317",
    )
    assert _otlp_export_endpoint(config) == "http://alloy:4317"


def test_otlp_export_endpoint_uses_tempo_when_otlp_empty() -> None:
    config = TracingConfig(otlp_endpoint="", tempo_enabled=True, tempo_endpoint="http://tempo:4317")
    assert _otlp_export_endpoint(config) == "http://tempo:4317"


def test_otlp_export_endpoint_empty_when_export_disabled() -> None:
    config = TracingConfig(otlp_endpoint="  ", tempo_enabled=False, tempo_endpoint="http://tempo:4317")
    assert _otlp_export_endpoint(config) == ""


def test_tracing_otlp_endpoint_reads_nested_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACING__OTLP_ENDPOINT", "http://alloy:4317")
    loaded = BaseSettings()
    assert loaded.tracing.otlp_endpoint == "http://alloy:4317"
