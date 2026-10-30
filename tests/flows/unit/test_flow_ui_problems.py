"""Publish gate интерфейса: каждый код проблемы, лимиты и точная локализация маркера.

Проблемы — это то, что редактор показывает маркерами и что запрещает сохранить flow:
пути к системным полям state, зарезервированные поля ввода, лимиты html-блоков и
страниц, битые ссылки на страницы, дубли полей и формы без действия.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.flow_ui.document import FlowUIDocument
from core.flow_ui.problems import (
    RESERVED_WRITE_FIELDS,
    FlowUILimits,
    FlowUIProblem,
    assert_flow_ui_publishable,
    flow_ui_problems,
)
from core.flow_ui.templates import flow_ui_templates
from core.models.i18n_models import Language
from core.state.mutation_policy import FROZEN_STATE_FIELDS
from core.types import JsonObject

LIMITS = FlowUILimits()


def _document(blocks: list[JsonObject], *extra_pages: JsonObject) -> FlowUIDocument:
    return FlowUIDocument.model_validate(
        {
            "start_page_id": "main",
            "pages": [{"page_id": "main", "blocks": blocks}, *extra_pages],
        }
    )


def _codes(problems: list[FlowUIProblem]) -> list[tuple[str, str | None, str | None]]:
    return [(problem.code, problem.page_id, problem.block_id) for problem in problems]


class TestReservedAndFrozen:
    def test_reserved_write_fields_cover_frozen_and_every_state_attribute(self) -> None:
        assert FROZEN_STATE_FIELDS <= RESERVED_WRITE_FIELDS
        assert {"content", "response", "files", "variables", "ui_action", "ui_slots"} <= RESERVED_WRITE_FIELDS
        assert "name" not in RESERVED_WRITE_FIELDS

    @pytest.mark.parametrize("path", ["task_id", "interrupt.payload", "node_history"])
    def test_frozen_path_in_any_marker_is_reported_once_at_the_block(self, path: str) -> None:
        problems = flow_ui_problems(
            _document(
                [
                    {
                        "type": "section",
                        "block_id": "wrap",
                        "blocks": [{"type": "text", "block_id": "t", "markdown": f"{{{path}}}"}],
                    }
                ]
            ),
            LIMITS,
        )
        assert _codes(problems) == [("frozen_path", "main", "t")]
        assert path in problems[0].message

    def test_frozen_path_via_visible_when_state_path_and_html_binding(self) -> None:
        problems = flow_ui_problems(
            _document(
                [
                    {"type": "divider", "block_id": "d", "visible_when": {"path": "current_nodes"}},
                    {"type": "json_view", "block_id": "j", "path": "prompt_history"},
                    {"type": "html", "block_id": "h", "source": "<p data-bind=\"session_id\"></p>"},
                ]
            ),
            LIMITS,
        )
        assert _codes(problems) == [
            ("frozen_path", "main", "d"),
            ("frozen_path", "main", "j"),
            ("frozen_path", "main", "h"),
        ]

    @pytest.mark.parametrize("field", ["response", "content", "files", "variables.x", "task_id"])
    def test_reserved_input_field(self, field: str) -> None:
        problems = flow_ui_problems(
            _document(
                [
                    {"type": "text_input", "block_id": "i", "field": field},
                    {"type": "button", "block_id": "b", "label": "Go", "action": {"name": "go"}},
                ]
            ),
            LIMITS,
        )
        codes = [problem.code for problem in problems]
        assert "reserved_field" in codes
        assert all(problem.block_id == "i" for problem in problems)

    def test_html_field_is_checked_like_an_input_field(self) -> None:
        problems = flow_ui_problems(
            _document([{"type": "html", "block_id": "h", "source": "<i></i>", "field": "response"}]),
            LIMITS,
        )
        assert _codes(problems) == [("reserved_field", "main", "h")]
        clean = flow_ui_problems(
            _document([{"type": "html", "block_id": "h", "source": "<i></i>", "field": "comment"}]),
            LIMITS,
        )
        assert clean == []

    def test_reading_a_reserved_but_not_frozen_field_is_allowed(self) -> None:
        document = _document([{"type": "text", "block_id": "t", "markdown": "{response} {files}"}])
        assert flow_ui_problems(document, LIMITS) == []


class TestBlockLevelRules:
    def test_unbalanced_template_blocks_publish_in_every_template_property(self) -> None:
        unbalanced = flow_ui_problems(
            _document(
                [
                    {"type": "text", "block_id": "t", "markdown": "Итого {total"},
                    {"type": "heading", "block_id": "h", "text": "Ок {total}"},
                    {
                        "type": "select",
                        "block_id": "s",
                        "field": "plan",
                        "options": [{"value": "a", "label": "Тариф {name"}],
                        "action": {"name": "pick"},
                    },
                    {
                        "type": "conversation",
                        "block_id": "conversation",
                        "settings": {"greeting": "Привет }", "suggested_prompts": ["{a}", "{b"]},
                    },
                ]
            ),
            LIMITS,
        )
        assert _codes(unbalanced) == [
            ("template_unbalanced", "main", "t"),
            ("template_unbalanced", "main", "s"),
            ("template_unbalanced", "main", "conversation"),
            ("template_unbalanced", "main", "conversation"),
        ]
        assert "Итого {total" in unbalanced[0].message
        with pytest.raises(ValueError, match="template_unbalanced|непарн|Непарн"):
            assert_flow_ui_publishable(
                _document([{"type": "text", "block_id": "t", "markdown": "{open"}]), LIMITS
            )

    def test_malformed_but_balanced_expression_is_not_a_problem(self) -> None:
        assert (
            flow_ui_problems(
                _document([{"type": "text", "block_id": "t", "markdown": "{total-1} { \"json\": 1 }"}]),
                LIMITS,
            )
            == []
        )

    def test_select_default_must_be_an_option(self) -> None:
        select: JsonObject = {
            "type": "select",
            "block_id": "s",
            "field": "plan",
            "options": [{"value": "free", "label": "Free"}, {"value": "pro", "label": "Pro"}],
            "action": {"name": "pick"},
        }
        assert flow_ui_problems(_document([{**select, "default": "pro"}]), LIMITS) == []
        assert _codes(flow_ui_problems(_document([{**select, "default": "vip"}]), LIMITS)) == [
            ("unknown_option", "main", "s")
        ]
        multi = flow_ui_problems(
            _document([{**select, "multiple": True, "default": ["free", "vip", "gold"]}]), LIMITS
        )
        assert [problem.code for problem in multi] == ["unknown_option", "unknown_option"]

    def test_link_page_must_exist_but_url_links_are_free(self) -> None:
        assert _codes(
            flow_ui_problems(
                _document([{"type": "link", "block_id": "l", "label": "Next", "url": "", "page_id": "nope"}]),
                LIMITS,
            )
        ) == [("unknown_page", "main", "l")]
        ok = _document(
            [{"type": "link", "block_id": "l", "label": "Next", "url": "", "page_id": "second"}],
            {"page_id": "second"},
        )
        assert flow_ui_problems(ok, LIMITS) == []
        assert flow_ui_problems(
            _document([{"type": "link", "block_id": "l", "label": "Docs", "url": "https://x"}]), LIMITS
        ) == []

    def test_button_page_must_exist(self) -> None:
        assert _codes(
            flow_ui_problems(
                _document(
                    [
                        {
                            "type": "button",
                            "block_id": "go",
                            "label": "Next",
                            "action": None,
                            "page_id": "nope",
                        }
                    ]
                ),
                LIMITS,
            )
        ) == [("unknown_page", "main", "go")]
        ok = _document(
            [
                {
                    "type": "button",
                    "block_id": "go",
                    "label": "Next",
                    "action": None,
                    "page_id": "second",
                }
            ],
            {"page_id": "second"},
        )
        assert flow_ui_problems(ok, LIMITS) == []

    def test_html_source_size_limit_counts_utf8_bytes(self) -> None:
        limits = FlowUILimits(max_html_source_bytes=1024)
        cyrillic = "я" * 600
        problems = flow_ui_problems(
            _document([{"type": "html", "block_id": "h", "source": cyrillic}]), limits
        )
        assert _codes(problems) == [("html_too_large", "main", "h")]
        assert flow_ui_problems(
            _document([{"type": "html", "block_id": "h", "source": "a" * 1024}]), limits
        ) == []


class TestPageLevelRules:
    def test_duplicate_field_points_at_the_second_writer(self) -> None:
        problems = flow_ui_problems(
            _document(
                [
                    {"type": "text_input", "block_id": "first", "field": "name"},
                    {
                        "type": "section",
                        "block_id": "s",
                        "blocks": [{"type": "text_input", "block_id": "second", "field": "name"}],
                    },
                    {"type": "button", "block_id": "b", "label": "Go", "action": {"name": "go"}},
                ]
            ),
            LIMITS,
        )
        assert _codes(problems) == [("duplicate_field", "main", "second")]
        assert "'first'" in problems[0].message

    def test_same_field_on_two_pages_is_not_a_duplicate(self) -> None:
        document = _document(
            [
                {"type": "text_input", "block_id": "a", "field": "name", "action": {"name": "save"}},
            ],
            {
                "page_id": "second",
                "blocks": [
                    {"type": "text_input", "block_id": "b", "field": "name", "action": {"name": "save"}},
                ],
            },
        )
        assert flow_ui_problems(document, LIMITS) == []

    def test_html_block_does_not_count_as_a_field_writer_for_duplicates(self) -> None:
        document = _document(
            [
                {"type": "text_input", "block_id": "a", "field": "name"},
                {"type": "html", "block_id": "h", "source": "<i></i>", "field": "name"},
            ]
        )
        assert flow_ui_problems(document, LIMITS) == []

    @pytest.mark.parametrize(
        "action_block",
        [
            {"type": "button", "block_id": "go", "label": "Go", "action": {"name": "go"}},
            {"type": "html", "block_id": "custom", "source": "<button>go</button>"},
        ],
    )
    def test_inputs_need_an_action_on_the_page(self, action_block: JsonObject) -> None:
        inputs: list[JsonObject] = [{"type": "text_input", "block_id": "i", "field": "name"}]
        assert _codes(flow_ui_problems(_document(inputs), LIMITS)) == [("no_action", "main", None)]
        assert flow_ui_problems(_document([*inputs, action_block]), LIMITS) == []
        with_own_action = _document(
            [{"type": "switch", "block_id": "sw", "field": "on", "action": {"name": "toggle"}}]
        )
        assert flow_ui_problems(with_own_action, LIMITS) == []
        assert flow_ui_problems(_document([{"type": "text", "block_id": "t", "markdown": "x"}]), LIMITS) == []

    def test_block_limits_count_nested_blocks(self) -> None:
        limits = FlowUILimits(max_blocks_per_page=3, max_html_blocks_per_page=1)
        document = _document(
            [
                {
                    "type": "section",
                    "block_id": "s",
                    "blocks": [
                        {"type": "html", "block_id": "h1", "source": "<i></i>"},
                        {"type": "html", "block_id": "h2", "source": "<i></i>"},
                    ],
                },
                {"type": "divider", "block_id": "d"},
            ]
        )
        assert _codes(flow_ui_problems(document, limits)) == [
            ("too_many_blocks", "main", None),
            ("too_many_html_blocks", "main", None),
        ]
        assert flow_ui_problems(document, FlowUILimits(max_blocks_per_page=4, max_html_blocks_per_page=2)) == []

    def test_page_limit(self) -> None:
        document = _document([], {"page_id": "second"}, {"page_id": "third"})
        problems = flow_ui_problems(document, FlowUILimits(max_pages=2))
        assert _codes(problems) == [("too_many_pages", None, None)]
        assert flow_ui_problems(document, FlowUILimits(max_pages=3)) == []


class TestGate:
    def test_publishable_document_passes(self) -> None:
        assert_flow_ui_publishable(
            _document([{"type": "conversation", "block_id": "c"}]), LIMITS
        )

    def test_error_message_names_first_problem_and_total(self) -> None:
        document = _document(
            [
                {"type": "text_input", "block_id": "i", "field": "task_id"},
                {"type": "text", "block_id": "t", "markdown": "{task_id}"},
            ]
        )
        with pytest.raises(ValueError) as exc:
            assert_flow_ui_publishable(document, LIMITS)
        assert str(exc.value).startswith("Flow UI: Путь 'task_id' указывает на системное поле state (main, i)")
        assert str(exc.value).endswith("total problems: 4")

    def test_document_level_problem_has_document_location(self) -> None:
        with pytest.raises(ValueError, match=r"\(document\); total problems: 1"):
            assert_flow_ui_publishable(
                _document([], {"page_id": "second"}), FlowUILimits(max_pages=1)
            )

    @pytest.mark.parametrize("locale", [Language.RU, Language.EN])
    def test_every_gallery_template_is_publishable(self, locale: Language) -> None:
        for template in flow_ui_templates(locale):
            assert flow_ui_problems(template.document, LIMITS) == [], template.template_id


class TestLimitsModel:
    def test_defaults(self) -> None:
        assert LIMITS.model_dump() == {
            "max_pages": 24,
            "max_blocks_per_page": 400,
            "max_blocks_per_render": 60,
            "max_state_bytes": 1_000_000,
            "max_html_source_bytes": 200_000,
            "max_html_blocks_per_page": 12,
        }

    @pytest.mark.parametrize(
        "payload",
        [
            {"max_pages": 0},
            {"max_pages": 101},
            {"max_blocks_per_render": 501},
            {"max_state_bytes": 1023},
            {"max_html_source_bytes": 5_000_001},
            {"max_html_blocks_per_page": 0},
            {"unknown": 1},
        ],
    )
    def test_bounds(self, payload: JsonObject) -> None:
        with pytest.raises(ValidationError):
            _ = FlowUILimits.model_validate(payload)
