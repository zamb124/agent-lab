"""Фикстуры грамматики (``schema.json``) и галереи (``templates.json``) совпадают с кодом."""

from __future__ import annotations

import json
from pathlib import Path

from core.flow_ui.document import FlowUIDocument
from core.flow_ui.templates import FlowUITemplate, flow_ui_templates
from core.pagination import OffsetPage
from core.state.mutation_policy import FROZEN_STATE_FIELDS

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "flow_ui" / "schema.json"
TEMPLATES_FIXTURE = FIXTURE.with_name("templates.json")


def test_schema_fixture_matches_grammar() -> None:
    expected = FlowUIDocument.model_json_schema()
    expected["x-flow-ui-frozen-state-fields"] = sorted(FROZEN_STATE_FIELDS)
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == expected, (
        "run: uv run python scripts/generate_flow_ui_schema_fixture.py"
    )


def test_templates_fixture_matches_gallery() -> None:
    templates = flow_ui_templates("en")
    expected = OffsetPage[FlowUITemplate](items=templates, total=len(templates), limit=200, offset=0)
    assert json.loads(TEMPLATES_FIXTURE.read_text(encoding="utf-8")) == expected.model_dump(mode="json"), (
        "run: uv run python scripts/generate_flow_ui_schema_fixture.py"
    )


def test_every_block_definition_is_tagged_for_the_editor() -> None:
    schema = json.loads(FIXTURE.read_text(encoding="utf-8"))
    block_defs = {
        name for name, definition in schema["$defs"].items() if "x-flow-ui-block" in definition
    }
    union_refs = {
        ref["$ref"].rsplit("/", 1)[1]
        for ref in schema["$defs"]["FlowUIPage"]["properties"]["blocks"]["items"]["oneOf"]
    }
    assert union_refs == block_defs
