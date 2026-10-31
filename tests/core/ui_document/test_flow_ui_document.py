"""Грамматика Flow UI: каждый блок, его лимиты и инварианты документа.

Pydantic-модели ``core/ui_document/document.py`` — единственная спецификация интерфейса, поэтому
здесь закреплены границы, на которые опираются редактор, тулы ``ui_render`` и валидация
сохранения flow: паттерны id и путей, обязательные поля, взаимоисключающие источники,
уникальность block_id внутри страницы и стартовая страница документа.
"""

from __future__ import annotations

from typing import cast

import pytest
from pydantic import TypeAdapter, ValidationError

from core.types import JsonObject
from core.ui_document.document import (
    ACTION_NAME_PATTERN,
    BLOCK_ID_PATTERN,
    INPUT_BLOCK_TYPES,
    PAGE_ID_PATTERN,
    STATE_PATH_PATTERN,
    FlowUIAgentIdentity,
    FlowUIBlock,
    FlowUIBlockModel,
    FlowUIConversation,
    FlowUIConversationSettings,
    FlowUIDocument,
    FlowUIInputBase,
    FlowUIInputBlock,
    FlowUIPage,
    FlowUISection,
    FlowUISlot,
    assert_unique_block_ids,
    input_field_type_name,
    iter_blocks,
)

BLOCK_ADAPTER: TypeAdapter[FlowUIBlockModel] = TypeAdapter(FlowUIBlock)

MINIMAL_BLOCKS: dict[str, JsonObject] = {
    "section": {"type": "section", "block_id": "b"},
    "columns": {"type": "columns", "block_id": "b", "columns": [{"width": 12}]},
    "tabs": {"type": "tabs", "block_id": "b", "tabs": [{"title": "T"}]},
    "heading": {"type": "heading", "block_id": "b", "text": "H"},
    "text": {"type": "text", "block_id": "b", "markdown": "m"},
    "image": {"type": "image", "block_id": "b", "url": "https://x/i.png"},
    "video": {"type": "video", "block_id": "b", "url": "https://x/v.mp4"},
    "audio": {"type": "audio", "block_id": "b", "url": "https://x/a.mp3"},
    "code": {"type": "code", "block_id": "b", "code": "x = 1"},
    "badge": {"type": "badge", "block_id": "b", "label": "New"},
    "alert": {"type": "alert", "block_id": "b", "message": "Careful"},
    "metric": {"type": "metric", "block_id": "b", "label": "Total", "value": "{total}"},
    "progress": {"type": "progress", "block_id": "b", "value": "{done}"},
    "status": {"type": "status", "block_id": "b", "label": "Ready"},
    "empty_state": {"type": "empty_state", "block_id": "b", "message": "Nothing"},
    "divider": {"type": "divider", "block_id": "b"},
    "text_input": {"type": "text_input", "block_id": "b", "field": "name"},
    "number_input": {"type": "number_input", "block_id": "b", "field": "count"},
    "select": {
        "type": "select",
        "block_id": "b",
        "field": "plan",
        "options": [{"value": "free", "label": "Free"}],
    },
    "checkbox": {"type": "checkbox", "block_id": "b", "field": "agree"},
    "switch": {"type": "switch", "block_id": "b", "field": "on"},
    "slider": {"type": "slider", "block_id": "b", "field": "level"},
    "date_input": {"type": "date_input", "block_id": "b", "field": "day"},
    "datetime_input": {"type": "datetime_input", "block_id": "b", "field": "moment"},
    "file_upload": {"type": "file_upload", "block_id": "b", "field": "attachments"},
    "voice_input": {"type": "voice_input", "block_id": "b", "field": "speech"},
    "button": {"type": "button", "block_id": "b", "label": "Go", "action": {"name": "go"}},
    "link": {"type": "link", "block_id": "b", "label": "Docs", "url": "https://x"},
    "data_table": {"type": "data_table", "block_id": "b", "rows": "rows"},
    "chart": {"type": "chart", "block_id": "b", "data": "points", "x": "day", "y": ["value"]},
    "json_view": {"type": "json_view", "block_id": "b", "path": "payload"},
    "file_card": {"type": "file_card", "block_id": "b", "file": "report"},
    "file_list": {"type": "file_list", "block_id": "b"},
    "conversation": {"type": "conversation", "block_id": "b"},
    "slot": {"type": "slot", "block_id": "b"},
    "agent_identity": {"type": "agent_identity", "block_id": "b"},
    "avatar": {"type": "avatar", "block_id": "b", "name": "Ann"},
    "run_trace": {"type": "run_trace", "block_id": "b"},
    "tool_activity": {"type": "tool_activity", "block_id": "b"},
    "browser_preview": {"type": "browser_preview", "block_id": "b", "url": "https://x"},
    "skill_activity": {
        "type": "skill_activity",
        "block_id": "b",
        "agent_skill_id": "crm-entities",
        "title": "CRM",
    },
    "action_preview": {"type": "action_preview", "block_id": "b", "title": "Create"},
    "action_result": {"type": "action_result", "block_id": "b", "title": "Created"},
    "reflection": {"type": "reflection", "block_id": "b", "text": "Hmm"},
    "activity": {"type": "activity", "block_id": "b", "title": "Working"},
    "suggested_prompts": {"type": "suggested_prompts", "block_id": "b", "items": ["Hi"]},
    "html": {"type": "html", "block_id": "b", "source": "<b>x</b>"},
}


def _block(payload: JsonObject) -> FlowUIBlockModel:
    return BLOCK_ADAPTER.validate_python(payload)


def _document(blocks: list[JsonObject], *, page_id: str = "main") -> FlowUIDocument:
    return FlowUIDocument.model_validate(
        {"start_page_id": page_id, "pages": [{"page_id": page_id, "blocks": blocks}]}
    )


def _grammar_types() -> set[str]:
    schema = BLOCK_ADAPTER.json_schema()
    return set(cast(dict[str, object], schema["discriminator"]["mapping"]).keys())


class TestBlockCatalog:
    def test_minimal_payload_exists_for_every_grammar_type(self) -> None:
        assert set(MINIMAL_BLOCKS) == _grammar_types()
        assert INPUT_BLOCK_TYPES < set(MINIMAL_BLOCKS)

    @pytest.mark.parametrize("block_type", sorted(MINIMAL_BLOCKS))
    def test_minimal_block_validates_and_dumps_back(self, block_type: str) -> None:
        block = _block(MINIMAL_BLOCKS[block_type])
        assert block.type == block_type
        dumped = block.model_dump(mode="json")
        assert dumped["type"] == block_type
        assert dumped["visible_when"] is None
        assert dumped["span"] == 12
        assert dumped["align"] == "start"
        assert dumped["valign"] == "start"
        for key, value in MINIMAL_BLOCKS[block_type].items():
            if isinstance(value, dict | list):
                continue
            assert dumped[key] == value
        assert BLOCK_ADAPTER.validate_python(dumped) == block

    @pytest.mark.parametrize("block_type", sorted(MINIMAL_BLOCKS))
    def test_unknown_property_is_rejected(self, block_type: str) -> None:
        with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs"):
            _block({**MINIMAL_BLOCKS[block_type], "unexpected": 1})

    def test_span_align_valign_bounds(self) -> None:
        block = _block({**MINIMAL_BLOCKS["heading"], "span": 6, "align": "center", "valign": "end"})
        assert block.span == 6 and block.align == "center" and block.valign == "end"
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["heading"], "span": 0})
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["heading"], "span": 13})
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["heading"], "align": "left"})
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["heading"], "valign": "middle"})

    @pytest.mark.parametrize("block_type", sorted(INPUT_BLOCK_TYPES))
    def test_input_blocks_share_field_contract(self, block_type: str) -> None:
        block = _block(MINIMAL_BLOCKS[block_type])
        assert isinstance(block, FlowUIInputBase)
        assert block.required is False and block.label == "" and block.action is None
        with pytest.raises(ValidationError):
            _block(
                {key: value for key, value in MINIMAL_BLOCKS[block_type].items() if key != "field"}
            )

    def test_input_field_type_name_matches_value_written_by_the_client(self) -> None:
        expected = {
            "text_input": "string",
            "number_input": "number",
            "select": "string",
            "checkbox": "boolean",
            "switch": "boolean",
            "slider": "number",
            "date_input": "string",
            "datetime_input": "string",
            "file_upload": "array",
            "voice_input": "string",
        }
        for block_type, type_name in expected.items():
            block = cast(FlowUIInputBlock, _block(MINIMAL_BLOCKS[block_type]))
            assert input_field_type_name(block) == type_name, block_type
        multi = cast(FlowUIInputBlock, _block({**MINIMAL_BLOCKS["select"], "multiple": True}))
        assert input_field_type_name(multi) == "array"

    def test_unknown_type_and_missing_type_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _block({"type": "carousel", "block_id": "b"})
        with pytest.raises(ValidationError):
            _block({"block_id": "b"})


class TestIdentifiers:
    @pytest.mark.parametrize("block_id", ["a", "a1", "a-b_c", "x" * 64])
    def test_valid_block_ids(self, block_id: str) -> None:
        assert _block({**MINIMAL_BLOCKS["divider"], "block_id": block_id}).block_id == block_id

    @pytest.mark.parametrize("block_id", ["", "A", "1a", "-a", "a b", "a.b", "x" * 65, "Ää"])
    def test_invalid_block_ids(self, block_id: str) -> None:
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["divider"], "block_id": block_id})

    @pytest.mark.parametrize("path", ["a", "_a", "a.b", "a.1", "a_b.c_d", "A.B"])
    def test_valid_state_paths(self, path: str) -> None:
        assert _block({**MINIMAL_BLOCKS["text_input"], "field": path}).field == path

    @pytest.mark.parametrize("path", ["", "1a", ".a", "a.", "a..b", "a b", "a[0]", "a-b", "a/b"])
    def test_invalid_state_paths(self, path: str) -> None:
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["text_input"], "field": path})
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["json_view"], "path": path})
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["divider"], "visible_when": {"path": path}})

    @pytest.mark.parametrize("name", ["submit", "go_1", "a"])
    def test_valid_action_names(self, name: str) -> None:
        block = _block({**MINIMAL_BLOCKS["button"], "action": {"name": name}})
        assert block.action.name == name  # pyright: ignore[reportAttributeAccessIssue]

    @pytest.mark.parametrize("name", ["", "Submit", "go-now", "1go", "go now", "x" * 65])
    def test_invalid_action_names(self, name: str) -> None:
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["button"], "action": {"name": name}})

    def test_patterns_are_the_ones_shared_with_the_frontend(self) -> None:
        assert STATE_PATH_PATTERN == r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)*$"
        assert BLOCK_ID_PATTERN == PAGE_ID_PATTERN == r"^[a-z][a-z0-9_-]*$"
        assert ACTION_NAME_PATTERN == r"^[a-z][a-z0-9_]*$"


class TestBlockInvariants:
    def test_slider_range_must_be_increasing(self) -> None:
        with pytest.raises(ValidationError, match="max must be greater than min"):
            _block({**MINIMAL_BLOCKS["slider"], "min": 5, "max": 5})
        with pytest.raises(ValidationError, match="max must be greater than min"):
            _block({**MINIMAL_BLOCKS["slider"], "min": 10, "max": 1})
        assert (
            _block({**MINIMAL_BLOCKS["slider"], "min": -1, "max": 1, "step": 0.5}).type == "slider"
        )
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["slider"], "step": 0})

    def test_number_input_step_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["number_input"], "step": -1})
        assert (
            _block({**MINIMAL_BLOCKS["number_input"], "min": 1, "max": 2, "default": 1.5}).type
            == "number_input"
        )

    def test_link_needs_exactly_one_target(self) -> None:
        assert _block({**MINIMAL_BLOCKS["link"], "url": "", "page_id": "next"}).page_id == "next"
        with pytest.raises(ValidationError, match="exactly one of page_id or url"):
            _block({**MINIMAL_BLOCKS["link"], "url": ""})
        with pytest.raises(ValidationError, match="exactly one of page_id or url"):
            _block({**MINIMAL_BLOCKS["link"], "page_id": "next"})

    def test_button_needs_exactly_one_click_target(self) -> None:
        assert _block({**MINIMAL_BLOCKS["button"], "action": None, "page_id": "next"}).page_id == "next"
        assert _block({**MINIMAL_BLOCKS["button"], "action": None, "url": "https://x"}).url == "https://x"
        with pytest.raises(ValidationError, match="exactly one of action, page_id or url"):
            _block({**MINIMAL_BLOCKS["button"], "action": None})
        with pytest.raises(ValidationError, match="exactly one of action, page_id or url"):
            _block({**MINIMAL_BLOCKS["button"], "page_id": "next"})

    def test_data_table_needs_exactly_one_source(self) -> None:
        assert (
            _block({"type": "data_table", "block_id": "t", "file_id": "{file_id}"}).file_id
            == "{file_id}"
        )
        with pytest.raises(ValidationError, match="exactly one of rows or file_id"):
            _block({"type": "data_table", "block_id": "t"})
        with pytest.raises(ValidationError, match="exactly one of rows or file_id"):
            _block({"type": "data_table", "block_id": "t", "rows": "rows", "file_id": "{f}"})

    def test_file_card_needs_exactly_one_source(self) -> None:
        assert _block({"type": "file_card", "block_id": "f", "file_id": "{f}"}).file is None
        with pytest.raises(ValidationError, match="exactly one of file or file_id"):
            _block({"type": "file_card", "block_id": "f"})
        with pytest.raises(ValidationError, match="exactly one of file or file_id"):
            _block({"type": "file_card", "block_id": "f", "file": "report", "file_id": "{f}"})

    @pytest.mark.parametrize("height", [24, 4000, "auto"])
    def test_html_height_bounds_accept(self, height: int | str) -> None:
        assert _block({**MINIMAL_BLOCKS["html"], "height": height}).height == height

    @pytest.mark.parametrize("height", [23, 4001, 0, -10, "big", "100px", 1.5])
    def test_html_height_bounds_reject(self, height: object) -> None:
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["html"], "height": height})

    def test_html_source_fields_and_field(self) -> None:
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["html"], "source": ""})
        block = _block({**MINIMAL_BLOCKS["html"], "fields": ["a", "b.c"], "field": "comment"})
        assert block.fields == ["a", "b.c"] and block.field == "comment"  # pyright: ignore[reportAttributeAccessIssue]
        assert (
            _block({**MINIMAL_BLOCKS["html"], "fields": [f"f{i}" for i in range(64)]}).type
            == "html"
        )
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["html"], "fields": [f"f{i}" for i in range(65)]})
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["html"], "fields": ["1bad"]})

    def test_container_cardinalities(self) -> None:
        with pytest.raises(ValidationError):
            _block({"type": "columns", "block_id": "c", "columns": []})
        with pytest.raises(ValidationError):
            _block({"type": "columns", "block_id": "c", "columns": [{"width": 6}] * 7})
        with pytest.raises(ValidationError):
            _block({"type": "columns", "block_id": "c", "columns": [{"width": 0}]})
        with pytest.raises(ValidationError):
            _block({"type": "columns", "block_id": "c", "columns": [{"width": 13}]})
        with pytest.raises(ValidationError):
            _block({"type": "tabs", "block_id": "t", "tabs": []})
        with pytest.raises(ValidationError):
            _block({"type": "tabs", "block_id": "t", "tabs": [{"title": "x"}] * 13})
        with pytest.raises(ValidationError):
            _block({"type": "tabs", "block_id": "t", "tabs": [{}]})

    def test_select_options_and_defaults(self) -> None:
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["select"], "options": []})
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["select"], "options": [{"value": "", "label": "x"}]})
        single = _block({**MINIMAL_BLOCKS["select"], "default": "free"})
        multi = _block({**MINIMAL_BLOCKS["select"], "multiple": True, "default": ["free"]})
        assert single.default == "free" and multi.default == ["free"]  # pyright: ignore[reportAttributeAccessIssue]

    def test_list_limits_of_prompts_chart_and_conversation(self) -> None:
        with pytest.raises(ValidationError):
            _block({"type": "suggested_prompts", "block_id": "p", "items": []})
        with pytest.raises(ValidationError):
            _block({"type": "suggested_prompts", "block_id": "p", "items": ["x"] * 13})
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["chart"], "y": []})
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["chart"], "y": ["a"] * 9})
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["chart"], "kind": "scatter"})
        with pytest.raises(ValidationError):
            _block(
                {
                    "type": "conversation",
                    "block_id": "c",
                    "settings": {"suggested_prompts": ["x"] * 13},
                }
            )
        with pytest.raises(ValidationError):
            _block({"type": "conversation", "block_id": "c", "settings": {"tool_calls": "verbose"}})

    def test_literal_properties_reject_foreign_values(self) -> None:
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["heading"], "level": 4})
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["badge"], "tone": "primary"})
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["button"], "variant": "link"})
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["progress"], "max": 0})
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["activity"], "status": "done"})

    def test_visible_when_condition(self) -> None:
        block = _block({**MINIMAL_BLOCKS["divider"], "visible_when": {"path": "status"}})
        assert block.visible_when is not None
        assert block.visible_when.equals is None
        block = _block(
            {**MINIMAL_BLOCKS["divider"], "visible_when": {"path": "status", "equals": {"a": [1]}}}
        )
        assert block.visible_when is not None and block.visible_when.equals == {"a": [1]}
        with pytest.raises(ValidationError):
            _block({**MINIMAL_BLOCKS["divider"], "visible_when": {"equals": 1}})

    def test_models_are_strict_on_assignment(self) -> None:
        block = _block(MINIMAL_BLOCKS["heading"])
        with pytest.raises(ValidationError):
            block.level = 7  # pyright: ignore[reportAttributeAccessIssue]


class TestTree:
    def _nested_page(self) -> FlowUIPage:
        return FlowUIPage.model_validate(
            {
                "page_id": "main",
                "blocks": [
                    {"type": "heading", "block_id": "h", "text": "Top"},
                    {
                        "type": "section",
                        "block_id": "s",
                        "blocks": [
                            {
                                "type": "columns",
                                "block_id": "c",
                                "columns": [
                                    {"width": 6, "blocks": [{"type": "slot", "block_id": "left"}]},
                                    {
                                        "width": 6,
                                        "blocks": [
                                            {
                                                "type": "tabs",
                                                "block_id": "t",
                                                "tabs": [
                                                    {
                                                        "title": "A",
                                                        "blocks": [
                                                            {
                                                                "type": "text_input",
                                                                "block_id": "deep",
                                                                "field": "deep",
                                                            }
                                                        ],
                                                    },
                                                    {"title": "B"},
                                                ],
                                            }
                                        ],
                                    },
                                ],
                            }
                        ],
                    },
                    {"type": "conversation", "block_id": "chat"},
                ],
            }
        )

    def test_iter_blocks_is_depth_first_and_includes_containers(self) -> None:
        page = self._nested_page()
        assert [block.block_id for block in iter_blocks(page.blocks)] == [
            "h",
            "s",
            "c",
            "left",
            "t",
            "deep",
            "chat",
        ]
        assert page.render_target_ids() == ["left", "chat"]

    def test_page_show_title_defaults_true(self) -> None:
        page = FlowUIPage.model_validate({"page_id": "main"})
        assert page.show_title is True
        assert page.title == ""
        hidden = FlowUIPage.model_validate({"page_id": "main", "show_title": False, "title": "Hi"})
        assert hidden.show_title is False and hidden.title == "Hi"

    def test_duplicate_block_id_is_rejected_at_any_depth(self) -> None:
        with pytest.raises(ValidationError, match="duplicate block_id 'deep'"):
            FlowUIPage.model_validate(
                {
                    "page_id": "main",
                    "blocks": [
                        {"type": "text_input", "block_id": "deep", "field": "x"},
                        {
                            "type": "section",
                            "block_id": "s",
                            "blocks": [
                                {
                                    "type": "tabs",
                                    "block_id": "t",
                                    "tabs": [
                                        {
                                            "title": "A",
                                            "blocks": [{"type": "divider", "block_id": "deep"}],
                                        }
                                    ],
                                }
                            ],
                        },
                    ],
                }
            )
        with pytest.raises(ValueError, match="slot 's': duplicate block_id 'x'"):
            assert_unique_block_ids(
                [
                    _block({"type": "divider", "block_id": "x"}),
                    _block({"type": "divider", "block_id": "x"}),
                ],
                scope="slot 's'",
            )

    def test_same_block_id_on_different_pages_is_allowed(self) -> None:
        document = FlowUIDocument.model_validate(
            {
                "start_page_id": "a",
                "pages": [
                    {"page_id": "a", "blocks": [{"type": "divider", "block_id": "same"}]},
                    {"page_id": "b", "blocks": [{"type": "divider", "block_id": "same"}]},
                ],
            }
        )
        assert [block.block_id for block in document.blocks()] == ["same", "same"]


class TestDocument:
    def test_start_page_must_exist_and_page_ids_unique(self) -> None:
        with pytest.raises(ValidationError, match="start_page_id 'missing' is not a page"):
            FlowUIDocument.model_validate(
                {"start_page_id": "missing", "pages": [{"page_id": "main"}]}
            )
        with pytest.raises(ValidationError, match="duplicate page_id"):
            FlowUIDocument.model_validate(
                {"start_page_id": "main", "pages": [{"page_id": "main"}, {"page_id": "main"}]}
            )
        with pytest.raises(ValidationError):
            FlowUIDocument.model_validate({"start_page_id": "main", "pages": []})
        with pytest.raises(ValidationError):
            FlowUIDocument.model_validate(
                {
                    "start_page_id": "p0",
                    "pages": [{"page_id": f"p{index}"} for index in range(101)],
                }
            )

    def test_page_lookup_and_block_helpers(self) -> None:
        document = FlowUIDocument.model_validate(
            {
                "start_page_id": "main",
                "pages": [
                    {
                        "page_id": "main",
                        "blocks": [
                            {"type": "text_input", "block_id": "name", "field": "name"},
                            {"type": "slot", "block_id": "s"},
                        ],
                    },
                    {
                        "page_id": "other",
                        "blocks": [{"type": "switch", "block_id": "on", "field": "on"}],
                    },
                ],
            }
        )
        assert document.page("other").page_id == "other"
        with pytest.raises(KeyError, match="no page 'nope'"):
            _ = document.page("nope")
        assert [block.block_id for block in document.input_blocks()] == ["name", "on"]
        assert [block.block_id for block in document.blocks()] == ["name", "s", "on"]

    def test_conversation_settings_come_from_the_first_feed(self) -> None:
        assert _document([]).conversation_settings() == FlowUIConversationSettings()
        document = _document(
            [
                {
                    "type": "section",
                    "block_id": "s",
                    "blocks": [
                        {"type": "conversation", "block_id": "c1", "settings": {"greeting": "one"}},
                    ],
                },
                {"type": "conversation", "block_id": "c2", "settings": {"greeting": "two"}},
            ]
        )
        assert document.conversation_settings().greeting == "one"

    def test_agent_identity_image_url_skips_empty(self) -> None:
        assert (
            _document([{"type": "agent_identity", "block_id": "a"}]).agent_identity_image_url()
            is None
        )
        document = _document(
            [
                {"type": "agent_identity", "block_id": "a"},
                {"type": "agent_identity", "block_id": "b", "image_url": "https://x/logo.png"},
            ]
        )
        assert document.agent_identity_image_url() == "https://x/logo.png"
        with pytest.raises(ValidationError):
            FlowUIAgentIdentity(block_id="a", image_url="x" * 2001)

    def test_embed_overrides_reach_nested_feeds_and_switch_start_page(self) -> None:
        document = FlowUIDocument.model_validate(
            {
                "start_page_id": "main",
                "pages": [
                    {
                        "page_id": "main",
                        "blocks": [
                            {"type": "conversation", "block_id": "top"},
                            {
                                "type": "section",
                                "block_id": "s",
                                "blocks": [{"type": "conversation", "block_id": "in-section"}],
                            },
                            {
                                "type": "columns",
                                "block_id": "c",
                                "columns": [
                                    {
                                        "width": 12,
                                        "blocks": [
                                            {"type": "conversation", "block_id": "in-column"}
                                        ],
                                    }
                                ],
                            },
                            {
                                "type": "tabs",
                                "block_id": "t",
                                "tabs": [
                                    {
                                        "title": "A",
                                        "blocks": [{"type": "conversation", "block_id": "in-tab"}],
                                    }
                                ],
                            },
                            {"type": "divider", "block_id": "d"},
                        ],
                    },
                    {"page_id": "second", "blocks": []},
                ],
            }
        )
        settings = FlowUIConversationSettings(greeting="Embedded", allow_voice=False)
        embedded = document.with_embed_overrides(conversation=settings, start_page_id="second")
        assert embedded.start_page_id == "second"
        feeds = [block for block in embedded.blocks() if isinstance(block, FlowUIConversation)]
        assert [block.block_id for block in feeds] == ["top", "in-section", "in-column", "in-tab"]
        assert all(block.settings == settings for block in feeds)
        assert document.conversation_settings() == FlowUIConversationSettings()

        untouched = document.with_embed_overrides(conversation=None, start_page_id=None)
        assert untouched == document
        with pytest.raises(ValidationError, match="start_page_id 'nope' is not a page"):
            _ = document.with_embed_overrides(conversation=None, start_page_id="nope")


class TestJsonSchema:
    def test_template_and_state_path_markers_are_exposed_to_the_editor(self) -> None:
        schema = FlowUIDocument.model_json_schema()
        definitions = cast(dict[str, JsonObject], schema["$defs"])
        heading = cast(dict[str, JsonObject], definitions["FlowUIHeading"]["properties"])
        assert heading["text"]["x-flow-ui"] == "template"
        text_input = cast(dict[str, JsonObject], definitions["FlowUITextInput"]["properties"])
        assert text_input["field"]["x-flow-ui"] == "state_path"
        assert text_input["field"]["pattern"] == STATE_PATH_PATTERN
        assert "x-flow-ui" not in text_input["pattern"]
        condition = cast(dict[str, JsonObject], definitions["FlowUICondition"]["properties"])
        assert condition["path"]["x-flow-ui"] == "state_path"
        html = cast(dict[str, JsonObject], definitions["FlowUIHtml"]["properties"])
        assert html["fields"]["items"]["x-flow-ui"] == "state_path"
        assert "x-flow-ui" not in html["source"]
        identity = cast(dict[str, JsonObject], definitions["FlowUIAgentIdentity"]["properties"])
        assert identity["image_url"]["x-flow-ui"] == "image_url"

    def test_every_block_declares_group_and_icon(self) -> None:
        schema = FlowUIDocument.model_json_schema()
        definitions = cast(dict[str, JsonObject], schema["$defs"])
        tagged = {
            name: cast(JsonObject, definition["x-flow-ui-block"])
            for name, definition in definitions.items()
            if "x-flow-ui-block" in definition
        }
        assert len(tagged) == len(MINIMAL_BLOCKS)
        groups = {cast(str, meta["group"]) for meta in tagged.values()}
        assert groups == {"layout", "content", "input", "action", "data", "platform", "custom"}
        assert tagged["FlowUIHtml"] == {"group": "custom", "icon": "terminal"}
        assert tagged["FlowUISection"] == {"group": "layout", "icon": "square"}
        assert all(cast(str, meta["icon"]) != "" for meta in tagged.values())


def test_slot_and_section_are_distinct_render_and_layout_roles() -> None:
    section = FlowUISection(block_id="s", blocks=[FlowUISlot(block_id="inner")])
    assert [block.block_id for block in iter_blocks([section])] == ["s", "inner"]
    assert isinstance(section.blocks[0], FlowUISlot)
