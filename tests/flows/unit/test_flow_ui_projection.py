"""Проекция state для клиента Flow UI (``apps/flows/src/flow_ui/projection``).

Клиент видит ровно те пути, на которые ссылается интерфейс и отрендеренные агентом блоки;
frozen-поля не проецируются никогда, списки отдаются целиком.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from apps.flows.src.flow_ui.projection import (
    assert_fields_outside_redacted,
    block_paths,
    block_templates,
    project_state,
    redact_state,
    referenced_paths,
    template_paths,
    validate_redacted_paths,
)
from apps.flows.src.state.mutation_policy import FROZEN_STATE_FIELDS
from core.ui_document.document import FlowUIBlock, FlowUIBlockModel, FlowUIDocument
from core.types import JsonObject

BLOCK_ADAPTER: TypeAdapter[FlowUIBlockModel] = TypeAdapter(FlowUIBlock)


def _block(payload: JsonObject) -> FlowUIBlockModel:
    return BLOCK_ADAPTER.validate_python(payload)


class TestTemplatePaths:
    def test_paths_are_deduplicated_in_order_of_appearance(self) -> None:
        assert template_paths("{b} {a.c} {b} {a}") == ["b", "a.c", "a"]

    def test_loop_bound_names_and_system_variables_are_not_state_paths(self) -> None:
        assert template_paths("{for item in items}{item.name}{/for}") == ["items"]
        assert template_paths("Сегодня {current_date}, {user_name}") == []
        assert template_paths("") == []
        assert template_paths("без переменных, \\{экранировано\\}") == []


class TestBlockPaths:
    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            ({"type": "heading", "block_id": "b", "text": "{title} / {sub.title}"}, ["title", "sub.title"]),
            ({"type": "text", "block_id": "b", "markdown": "{a}{a}"}, ["a"]),
            ({"type": "image", "block_id": "b", "url": "{img}", "alt": "{alt}"}, ["img", "alt"]),
            ({"type": "code", "block_id": "b", "code": "{snippet}", "language": "py"}, ["snippet"]),
            ({"type": "metric", "block_id": "b", "label": "{l}", "value": "{v}", "hint": "{h}"}, ["l", "v", "h"]),
            ({"type": "progress", "block_id": "b", "value": "{done}", "label": "{label}"}, ["label", "done"]),
            ({"type": "text_input", "block_id": "b", "field": "name", "label": "{label}", "placeholder": "{ph}", "default": "{d}", "error_message": "{err}"}, ["name", "label", "err", "ph", "d"]),
            ({"type": "select", "block_id": "b", "field": "plan", "options": [{"value": "x", "label": "{opt}"}]}, ["plan", "opt"]),
            ({"type": "button", "block_id": "b", "label": "{cta}", "action": {"name": "go"}}, ["cta"]),
            ({"type": "link", "block_id": "b", "label": "{l}", "url": "{u}"}, ["l", "u"]),
            ({"type": "data_table", "block_id": "b", "rows": "table.rows"}, ["table.rows"]),
            ({"type": "data_table", "block_id": "b", "file_id": "{report.file_id}"}, ["report.file_id", "files"]),
            ({"type": "chart", "block_id": "b", "data": "points", "x": "day", "y": ["value"], "title": "{t}"}, ["t", "points"]),
            ({"type": "json_view", "block_id": "b", "path": "payload", "title": "{t}"}, ["payload", "t"]),
            ({"type": "file_card", "block_id": "b", "file": "report"}, ["report"]),
            ({"type": "file_card", "block_id": "b", "file_id": "{fid}"}, ["fid", "files"]),
            ({"type": "file_list", "block_id": "b"}, ["files"]),
            ({"type": "file_list", "block_id": "b", "files": "attachments"}, ["attachments"]),
            ({"type": "conversation", "block_id": "b", "settings": {"greeting": "{hello}", "suggested_prompts": ["{p1}", "static"], "placeholder": "{ph}"}}, ["hello", "p1", "ph"]),
            ({"type": "avatar", "block_id": "b", "name": "{n}", "image_url": "{img}"}, ["n", "img"]),
            ({"type": "browser_preview", "block_id": "b", "url": "{u}", "title": "{t}", "screenshot_url": "{s}"}, ["u", "t", "s"]),
            ({"type": "suggested_prompts", "block_id": "b", "items": ["{a}", "{b}", "{a}"]}, ["a", "b"]),
            ({"type": "divider", "block_id": "b", "visible_when": {"path": "flags.show"}}, ["flags.show"]),
            ({"type": "html", "block_id": "b", "source": "<p data-bind=\"order.total\"></p><i data-show=\"ready\"></i>", "fields": ["comment"], "field": "comment"}, ["comment", "order.total", "ready"]),
            ({"type": "html", "block_id": "b", "source": "<p data-bind=\"x\"></p>", "fields": ["x"]}, ["x"]),
            ({"type": "slot", "block_id": "b"}, []),
            ({"type": "divider", "block_id": "b"}, []),
            ({"type": "run_trace", "block_id": "b"}, []),
        ],
    )
    def test_block_paths_follow_markers(self, payload: JsonObject, expected: list[str]) -> None:
        assert block_paths(_block(payload)) == expected

    def test_block_templates_lists_raw_template_strings_without_children(self) -> None:
        select = _block(
            {
                "type": "select",
                "block_id": "s",
                "field": "plan",
                "label": "Тариф {who}",
                "options": [{"value": "a", "label": "A {a}"}, {"value": "b", "label": "B"}],
                "action": {"name": "pick"},
            }
        )
        assert block_templates(select) == ["Тариф {who}", "A {a}", "B"]
        section = _block(
            {
                "type": "section",
                "block_id": "s",
                "title": "{section_title}",
                "blocks": [{"type": "text", "block_id": "t", "markdown": "{inner}"}],
            }
        )
        assert block_templates(section) == ["{section_title}"]
        assert block_templates(_block({"type": "divider", "block_id": "d"})) == []
        assert block_templates(_block({"type": "json_view", "block_id": "j", "path": "deep"})) == []

    def test_containers_do_not_leak_child_paths(self) -> None:
        section = _block(
            {
                "type": "section",
                "block_id": "s",
                "title": "{section_title}",
                "blocks": [{"type": "text", "block_id": "t", "markdown": "{inner}"}],
            }
        )
        assert block_paths(section) == ["section_title"]
        tabs = _block(
            {
                "type": "tabs",
                "block_id": "t",
                "tabs": [{"title": "{tab}", "blocks": [{"type": "text", "block_id": "x", "markdown": "{inner}"}]}],
            }
        )
        assert block_paths(tabs) == ["tab"]
        columns = _block(
            {
                "type": "columns",
                "block_id": "c",
                "columns": [{"width": 12, "blocks": [{"type": "json_view", "block_id": "j", "path": "deep"}]}],
                "visible_when": {"path": "show"},
            }
        )
        assert block_paths(columns) == ["show"]

    def test_referenced_paths_union_document_and_rendered_slots(self) -> None:
        document = FlowUIDocument.model_validate(
            {
                "start_page_id": "main",
                "pages": [
                    {
                        "page_id": "main",
                        "blocks": [
                            {"type": "text", "block_id": "t", "markdown": "{greeting}"},
                            {
                                "type": "section",
                                "block_id": "s",
                                "blocks": [{"type": "text_input", "block_id": "n", "field": "name"}],
                            },
                            {"type": "slot", "block_id": "details"},
                        ],
                    },
                    {"page_id": "second", "blocks": [{"type": "metric", "block_id": "m", "label": "x", "value": "{total}"}]},
                ],
            }
        )
        rendered = {
            "details": [
                _block(
                    {
                        "type": "section",
                        "block_id": "inner",
                        "blocks": [{"type": "json_view", "block_id": "j", "path": "payload"}],
                    }
                )
            ]
        }
        assert referenced_paths(document, {}) == frozenset({"greeting", "name", "total"})
        assert referenced_paths(document, rendered) == frozenset({"greeting", "name", "total", "payload"})


class TestProjectState:
    PAYLOAD: JsonObject = {
        "name": "Ann",
        "order": {"total": 10, "items": [{"sku": "a"}, {"sku": "b"}], "meta": {"tag": "x", "hidden": 1}},
        "flags": None,
        "task_id": "tsk",
        "files": [{"file_id": "f1"}],
    }

    def test_projection_keeps_only_requested_paths(self) -> None:
        assert project_state(self.PAYLOAD, {"name", "order.total"}) == {
            "name": "Ann",
            "order": {"total": 10},
        }

    def test_missing_paths_and_scalar_descent_are_skipped(self) -> None:
        assert project_state(self.PAYLOAD, {"missing", "name.first", "order.absent.deep"}) == {}

    def test_frozen_roots_never_leak(self) -> None:
        assert project_state(self.PAYLOAD, {"task_id", "task_id.x", "name"}) == {"name": "Ann"}
        assert "files" not in FROZEN_STATE_FIELDS

    def test_list_stops_descent_and_is_returned_whole(self) -> None:
        assert project_state(self.PAYLOAD, {"order.items.0.sku"}) == {
            "order": {"items": [{"sku": "a"}, {"sku": "b"}]}
        }
        assert project_state(self.PAYLOAD, {"files.file_id", "files"}) == {"files": [{"file_id": "f1"}]}

    def test_parent_path_absorbs_children_and_null_is_a_value(self) -> None:
        assert project_state(self.PAYLOAD, {"order.meta.tag", "order.meta", "order.total"}) == {
            "order": {"meta": {"tag": "x", "hidden": 1}, "total": 10}
        }
        assert project_state(self.PAYLOAD, {"flags"}) == {"flags": None}

    def test_projection_is_a_copy_of_the_payload(self) -> None:
        projected = project_state(self.PAYLOAD, {"order.meta.tag"})
        projected["order"]["meta"]["tag"] = "changed"  # pyright: ignore[reportIndexIssue, reportArgumentType]
        assert self.PAYLOAD["order"]["meta"]["tag"] == "x"  # pyright: ignore[reportIndexIssue, reportArgumentType]

    def test_empty_paths_produce_empty_projection(self) -> None:
        assert project_state(self.PAYLOAD, frozenset()) == {}


class TestRedaction:
    def test_validate_normalizes_and_deduplicates(self) -> None:
        assert validate_redacted_paths([" /secret ", "/secret", "/a~1b/c", "/nested/deep"]) == [
            "/secret",
            "/a~1b/c",
            "/nested/deep",
        ]
        assert validate_redacted_paths([]) == []

    @pytest.mark.parametrize("pointer", ["", "/", "   ", "//x"])
    def test_validate_rejects_pointers_without_a_field(self, pointer: str) -> None:
        with pytest.raises(ValueError, match="must point to a state field"):
            _ = validate_redacted_paths([pointer])

    def test_validate_rejects_frozen_roots_and_bad_pointers(self) -> None:
        with pytest.raises(ValueError, match="cannot target a system field"):
            _ = validate_redacted_paths(["/task_id"])
        with pytest.raises(ValueError, match="cannot target a system field"):
            _ = validate_redacted_paths(["/interrupt/payload"])
        with pytest.raises(ValueError, match="must start with '/'"):
            _ = validate_redacted_paths(["secret"])

    def test_redact_removes_nested_values_without_touching_the_source(self) -> None:
        projection: JsonObject = {"a": {"b": {"secret": 1, "keep": 2}, "c": 3}, "d": 4}
        redacted = redact_state(projection, ["/a/b/secret", "/d", "/missing", "/a/c/deep", "/a/nope/x"])
        assert redacted == {"a": {"b": {"keep": 2}, "c": 3}}
        assert projection == {"a": {"b": {"secret": 1, "keep": 2}, "c": 3}, "d": 4}
        assert redact_state(projection, []) == projection

    def test_fields_outside_redacted(self) -> None:
        assert_fields_outside_redacted(["name", "order.total", "secrets_"], ["/secret", "/order/notes"])
        with pytest.raises(PermissionError, match="'/secret'"):
            assert_fields_outside_redacted(["secret"], ["/secret"])
        with pytest.raises(PermissionError, match="'/order'"):
            assert_fields_outside_redacted(["order.total"], ["/order"])
        with pytest.raises(PermissionError, match="'/order/notes'"):
            assert_fields_outside_redacted(["order"], ["/order/notes"])
        assert_fields_outside_redacted([], ["/secret"])
        assert_fields_outside_redacted(["a/b"], ["/a"])
