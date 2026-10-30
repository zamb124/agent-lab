"""Страница ``docs/api/flows/flow-ui-protocol.md`` и conformance-фикстуры — один источник.

Каждый JSON-блок страницы с заголовком ``tests/fixtures/flow_ui/<file>#<selector>`` обязан
совпадать с указанным фрагментом фикстуры; константы sandbox — с ``html_sandbox.json``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast, get_args

import pytest

from apps.flows.src.flow_ui.html_bindings import HTML_BIND_ATTRIBUTE, HTML_SHOW_ATTRIBUTE
from core.ui_document.document import FlowUIBlock
from core.types import JsonValue, require_json_array, require_json_object

ROOT = Path(__file__).resolve().parents[3]
PAGE = ROOT / "docs" / "api" / "flows" / "flow-ui-protocol.md"
FIXTURES = ROOT / "tests" / "fixtures" / "flow_ui"

FENCE = re.compile(
    r'```json title="tests/fixtures/flow_ui/([a-z_]+\.json)#([^"]+)"\n(.*?)\n```', re.DOTALL
)
SELECTOR_STEP = re.compile(r"([a-z_]+)|\[(\d+)\]")


def _select(value: JsonValue, selector: str) -> JsonValue:
    """``cases[0].operations`` → фикстура["cases"][0]["operations"]."""
    current = value
    for key, index in SELECTOR_STEP.findall(selector):
        if key:
            current = require_json_object(current, f"selector {selector!r}")[key]
        else:
            current = require_json_array(current, f"selector {selector!r}")[int(index)]
    return current


def _page_examples() -> list[tuple[str, str, JsonValue]]:
    text = PAGE.read_text(encoding="utf-8")
    examples = [
        (fixture_name, selector, cast(JsonValue, json.loads(body)))
        for fixture_name, selector, body in FENCE.findall(text)
    ]
    if len(examples) < 3:
        raise AssertionError("protocol page must carry at least three fixture-pinned JSON examples")
    return examples


@pytest.mark.parametrize(("fixture_name", "selector", "example"), _page_examples())
def test_page_examples_equal_fixtures(fixture_name: str, selector: str, example: JsonValue) -> None:
    fixture = cast(JsonValue, json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8")))
    assert example == _select(fixture, selector), f"{fixture_name}#{selector} drifted from the page"


def test_page_states_sandbox_constants_from_fixture() -> None:
    sandbox = require_json_object(
        cast(object, json.loads((FIXTURES / "html_sandbox.json").read_text(encoding="utf-8"))),
        "html_sandbox fixture",
    )
    text = PAGE.read_text(encoding="utf-8")
    assert f'sandbox="{sandbox["sandbox"]}"' in text
    assert str(sandbox["csp"]) in text
    assert HTML_BIND_ATTRIBUTE in text and HTML_SHOW_ATTRIBUTE in text


def test_page_lists_every_grammar_block_type() -> None:
    union = get_args(FlowUIBlock)[0]
    block_types = {str(model.model_fields["type"].default) for model in get_args(union)}
    text = PAGE.read_text(encoding="utf-8")
    missing = sorted(block_type for block_type in block_types if f"`{block_type}`" not in text)
    assert missing == [], f"block types absent from the protocol page: {missing}"
