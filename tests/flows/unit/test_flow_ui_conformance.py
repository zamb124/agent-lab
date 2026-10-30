"""Conformance Flow UI протокола: фикстуры ``tests/fixtures/flow_ui`` общие с JS unit-тестами.

Каждая фикстура — часть спецификации ``docs/.../flow-ui-protocol.md``: грамматика
шаблонов, RFC 6902 патчи state, Part ``ui-action``, события артефакта ``ui`` и
sandbox блока ``html``. Python и JS обязаны читать одни и те же данные одинаково.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from pydantic import TypeAdapter, ValidationError

from apps.flows.src.flow_ui.action import ui_action_from_message
from apps.flows.src.flow_ui.html_bindings import (
    HTML_BIND_ATTRIBUTE,
    HTML_SHOW_ATTRIBUTE,
    html_bound_paths,
)
from apps.flows.src.flow_ui.problems import FlowUILimits, flow_ui_problems
from apps.flows.src.flow_ui.projection import template_paths
from core.a2a.codec import message_from_json_dict
from core.ui_document.document import FlowUIDocument
from core.ui_document.json_patch import apply_json_patch, json_patch_operations
from core.ui_document.protocol import (
    FLOW_UI_ACTION_MEDIA_TYPE,
    FLOW_UI_MEDIA_TYPE,
    JSON_MEDIA_TYPE,
    JSON_PATCH_MEDIA_TYPE,
    FlowUIActionMessage,
    FlowUIEvent,
    JsonPatchOperation,
)
from core.types import JsonObject
from core.variables.resolver import VariableMap, VariableResolver
from core.variables.template_scan import UnmatchedBracesError, unmatched_brace_message

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "flow_ui"
HTML_SANDBOX_SOURCE = (
    Path(__file__).resolve().parents[3] / "core/frontend/static/lib/flow-ui/runtime/html-sandbox.ts"
)


def _fixture(name: str) -> JsonObject:
    return cast(JsonObject, json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def _cases(fixture: JsonObject, key: str) -> list[JsonObject]:
    return cast(list[JsonObject], fixture[key])


class TestTemplating:
    def test_paths_and_text_match_fixture(self) -> None:
        for case in _cases(_fixture("templating.json"), "cases"):
            template = cast(str, case["template"])
            assert template_paths(template) == case["paths"], case["name"]
            if "text" in case:
                state = cast(VariableMap, case["state"])
                rendered = VariableResolver.render_template(
                    template, local_vars=state, include_system=False
                )
                assert rendered == case["text"], case["name"]

    def test_unbalanced_templates_fail_render_and_publish_gate(self) -> None:
        for template in cast(list[str], _fixture("templating.json")["unbalanced_templates"]):
            assert unmatched_brace_message(template) is not None, template
            with pytest.raises(UnmatchedBracesError):
                _ = VariableResolver.render_template(template, local_vars={}, include_system=False)
            document = FlowUIDocument.model_validate(
                {
                    "start_page_id": "main",
                    "pages": [
                        {
                            "page_id": "main",
                            "blocks": [{"type": "text", "block_id": "note", "markdown": template}],
                        }
                    ]
                }
            )
            codes = [problem.code for problem in flow_ui_problems(document, FlowUILimits())]
            assert codes == ["template_unbalanced"], template


class TestStatePatch:
    def test_diff_and_apply_match_fixture(self) -> None:
        adapter = TypeAdapter(list[JsonPatchOperation])
        for case in _cases(_fixture("state_patch.json"), "cases"):
            before = cast(JsonObject, case["before"])
            after = cast(JsonObject, case["after"])
            operations = json_patch_operations(before, after)
            assert adapter.dump_python(operations) == case["operations"], case["name"]
            assert apply_json_patch(before, adapter.validate_python(case["operations"])) == after, (
                case["name"]
            )

    def test_patch_serialization_omits_value_for_remove(self) -> None:
        operation = JsonPatchOperation(op="remove", path="/x")
        assert operation.model_dump() == {"op": "remove", "path": "/x"}


class TestUiActionMessage:
    def test_single_action_part_is_parsed(self) -> None:
        fixture = _fixture("ui_action_message.json")
        part = cast(JsonObject, fixture["part"])
        assert part["mediaType"] == FLOW_UI_ACTION_MEDIA_TYPE
        message = message_from_json_dict({"role": "ROLE_USER", "messageId": "m-1", "parts": [part]})
        action = ui_action_from_message(message)
        assert action == FlowUIActionMessage.model_validate(fixture["action"])
        assert action is not None
        assert action.to_state_action().model_dump() == fixture["state_action"]

    def test_text_message_has_no_action(self) -> None:
        message = message_from_json_dict(
            {"role": "ROLE_USER", "messageId": "m-1", "parts": [{"text": "hi"}]}
        )
        assert ui_action_from_message(message) is None

    def test_rejected_messages_raise(self) -> None:
        fixture = _fixture("ui_action_message.json")
        for name, payload in cast(dict[str, JsonObject], fixture["rejected_messages"]).items():
            with pytest.raises(ValueError):
                ui_action_from_message(message_from_json_dict(payload))
            assert name


class TestUiArtifacts:
    def test_document_render_and_navigate_validate(self) -> None:
        fixture = _fixture("ui_artifacts.json")
        document = FlowUIDocument.model_validate(fixture["document"])
        assert document.start_page_id == "main"
        events = TypeAdapter(FlowUIEvent)
        render = events.validate_python(fixture["render"])
        navigate = events.validate_python(fixture["navigate"])
        assert render.kind == "render" and navigate.kind == "navigate"
        assert {page.page_id for page in document.pages} >= {navigate.page_id}

    def test_parts_carry_declared_media_types(self) -> None:
        fixture = _fixture("ui_artifacts.json")
        kinds_by_media_type = {
            JSON_MEDIA_TYPE: "json",
            JSON_PATCH_MEDIA_TYPE: "json_patch",
            FLOW_UI_MEDIA_TYPE: "ui",
        }
        decoded: list[str] = []
        events = TypeAdapter(FlowUIEvent)
        for part in _cases(fixture, "parts"):
            if "text" in part:
                decoded.append("text")
                continue
            kind = kinds_by_media_type[cast(str, part["mediaType"])]
            if kind == "ui":
                events.validate_python(part["data"])
            decoded.append(kind)
        assert decoded == fixture["decoded_kinds"]

    def test_rejected_events_fail_validation(self) -> None:
        events = TypeAdapter(FlowUIEvent)
        for payload in _cases(_fixture("ui_artifacts.json"), "rejected_events"):
            with pytest.raises(ValidationError):
                events.validate_python(payload)


class TestHtmlSandbox:
    def test_attributes_and_bound_paths_match_fixture(self) -> None:
        fixture = _fixture("html_sandbox.json")
        assert fixture["bind_attribute"] == HTML_BIND_ATTRIBUTE
        assert fixture["show_attribute"] == HTML_SHOW_ATTRIBUTE
        for case in _cases(fixture, "bound_paths_cases"):
            assert html_bound_paths(cast(str, case["source"])) == case["paths"], case["name"]
        for source in cast(list[str], fixture["invalid_sources"]):
            with pytest.raises(ValueError):
                html_bound_paths(source)

    def test_frontend_constants_match_fixture(self) -> None:
        fixture = _fixture("html_sandbox.json")
        source = HTML_SANDBOX_SOURCE.read_text(encoding="utf-8")
        assert f'export const FLOW_UI_HTML_CSP = "{fixture["csp"]}";' in source
        assert f"export const FLOW_UI_HTML_SANDBOX = '{fixture['sandbox']}';" in source
        assert "allow-same-origin" not in cast(str, fixture["sandbox"])
        assert "unsafe-eval" not in cast(str, fixture["csp"])
