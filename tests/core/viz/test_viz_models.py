"""Unit-тесты контракта VizDocument."""

from __future__ import annotations

import json

import pytest

from core.viz.models import (
    VIZ_CONTENT_TYPE,
    VizDocument,
    VizEngine,
    VizKind,
    parse_viz_document_bytes,
    resolve_viz_engine,
)


def test_resolve_viz_engine_defaults() -> None:
    assert resolve_viz_engine(VizKind.CHART, None) == VizEngine.ECHARTS
    assert resolve_viz_engine(VizKind.FLOWCHART, None) == VizEngine.MERMAID
    assert resolve_viz_engine(VizKind.GANTT, VizEngine.ECHARTS) == VizEngine.ECHARTS


def test_parse_viz_mermaid_document() -> None:
    payload = {
        "schema_version": 1,
        "kind": "flowchart",
        "engine": "mermaid",
        "title": "Onboarding",
        "spec": {"source": "flowchart TD\n  A-->B"},
    }
    document = parse_viz_document_bytes(json.dumps(payload).encode("utf-8"))
    assert document.kind == VizKind.FLOWCHART
    assert document.engine == VizEngine.MERMAID
    assert document.spec["source"].startswith("flowchart")


def test_parse_viz_echarts_requires_option() -> None:
    payload = {
        "schema_version": 1,
        "kind": "chart",
        "engine": "echarts",
        "title": "Sales",
        "spec": {},
    }
    with pytest.raises(ValueError, match="option"):
        VizDocument.model_validate(payload)


def test_viz_content_type_constant() -> None:
    assert VIZ_CONTENT_TYPE == "application/vnd.platform.viz+json"
