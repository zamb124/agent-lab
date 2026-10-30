"""Publish gate интерфейса flow: проблемы документа, которые редактор показывает маркерами.

Структурная валидность обеспечивает Pydantic-грамматика; здесь — правила, для
которых нужен контекст всего документа и платформы: зарезервированные поля state,
достижимость действий, ссылки на страницы, лимиты ``html``.
"""

from __future__ import annotations

from apps.flows.src.flow_ui.limits import FlowUILimits
from apps.flows.src.flow_ui.projection import block_paths, block_templates
from apps.flows.src.state.execution_state import ExecutionState
from apps.flows.src.state.mutation_policy import FROZEN_STATE_FIELDS
from core.models.base import StrictBaseModel
from core.ui_document.document import (
    FlowUIBlockModel,
    FlowUIButton,
    FlowUIDocument,
    FlowUIHtml,
    FlowUIInputBase,
    FlowUILink,
    FlowUIPage,
    FlowUISelect,
    iter_blocks,
)
from core.variables.template_scan import unmatched_brace_message

RESERVED_WRITE_FIELDS: frozenset[str] = FROZEN_STATE_FIELDS | frozenset(ExecutionState.model_fields)


class FlowUIProblem(StrictBaseModel):
    code: str
    message: str
    page_id: str | None = None
    block_id: str | None = None


def _write_root(path: str) -> str:
    return path.split(".", 1)[0]


def _block_problems(
    block: FlowUIBlockModel,
    *,
    page: FlowUIPage,
    page_ids: set[str],
    limits: FlowUILimits,
) -> list[FlowUIProblem]:
    problems: list[FlowUIProblem] = []

    def problem(code: str, message: str) -> None:
        problems.append(
            FlowUIProblem(code=code, message=message, page_id=page.page_id, block_id=block.block_id)
        )

    for template in block_templates(block):
        brace_problem = unmatched_brace_message(template)
        if brace_problem is not None:
            # Рендер такого шаблона падает у зрителя, поэтому документ не публикуется
            problem("template_unbalanced", f"Шаблон {template!r}: {brace_problem}")
    for path in block_paths(block):
        if _write_root(path) in FROZEN_STATE_FIELDS:
            problem("frozen_path", f"Путь {path!r} указывает на системное поле state")
    if isinstance(block, FlowUIInputBase) and _write_root(block.field) in RESERVED_WRITE_FIELDS:
        problem("reserved_field", f"Поле {block.field!r} зарезервировано платформой")
    if isinstance(block, FlowUIHtml):
        if block.field is not None and _write_root(block.field) in RESERVED_WRITE_FIELDS:
            problem("reserved_field", f"Поле {block.field!r} зарезервировано платформой")
        if len(block.source.encode("utf-8")) > limits.max_html_source_bytes:
            problem(
                "html_too_large",
                f"HTML-блок больше {limits.max_html_source_bytes} байт",
            )
    if isinstance(block, FlowUISelect) and block.default is not None:
        allowed = {option.value for option in block.options}
        defaults = block.default if isinstance(block.default, list) else [block.default]
        for value in defaults:
            if value not in allowed:
                problem("unknown_option", f"Значение по умолчанию {value!r} отсутствует в options")
    if (
        isinstance(block, (FlowUILink, FlowUIButton))
        and block.page_id is not None
        and block.page_id not in page_ids
    ):
        problem("unknown_page", f"Переход ведёт на несуществующую страницу {block.page_id!r}")
    return problems


def _page_problems(
    page: FlowUIPage, *, page_ids: set[str], limits: FlowUILimits
) -> list[FlowUIProblem]:
    problems: list[FlowUIProblem] = []
    blocks = iter_blocks(page.blocks)
    if len(blocks) > limits.max_blocks_per_page:
        problems.append(
            FlowUIProblem(
                code="too_many_blocks",
                message=f"На странице больше {limits.max_blocks_per_page} блоков",
                page_id=page.page_id,
            )
        )
    html_count = sum(1 for block in blocks if isinstance(block, FlowUIHtml))
    if html_count > limits.max_html_blocks_per_page:
        problems.append(
            FlowUIProblem(
                code="too_many_html_blocks",
                message=f"На странице больше {limits.max_html_blocks_per_page} HTML-блоков",
                page_id=page.page_id,
            )
        )
    fields_seen: dict[str, str] = {}
    has_inputs = False
    has_action = False
    for block in blocks:
        problems.extend(_block_problems(block, page=page, page_ids=page_ids, limits=limits))
        if isinstance(block, FlowUIInputBase):
            has_inputs = True
            if block.action is not None:
                has_action = True
            owner = fields_seen.get(block.field)
            if owner is not None:
                problems.append(
                    FlowUIProblem(
                        code="duplicate_field",
                        message=f"Поле {block.field!r} уже пишет блок {owner!r}",
                        page_id=page.page_id,
                        block_id=block.block_id,
                    )
                )
            fields_seen[block.field] = block.block_id
        if isinstance(block, FlowUIButton):
            has_action = True
        if isinstance(block, FlowUIHtml):
            has_action = True
    if has_inputs and not has_action:
        problems.append(
            FlowUIProblem(
                code="no_action",
                message="На странице есть поля ввода, но нет действия, которое их отправит",
                page_id=page.page_id,
            )
        )
    return problems


def flow_ui_problems(document: FlowUIDocument, limits: FlowUILimits) -> list[FlowUIProblem]:
    problems: list[FlowUIProblem] = []
    if len(document.pages) > limits.max_pages:
        problems.append(
            FlowUIProblem(code="too_many_pages", message=f"Больше {limits.max_pages} страниц")
        )
    page_ids = {page.page_id for page in document.pages}
    for page in document.pages:
        problems.extend(_page_problems(page, page_ids=page_ids, limits=limits))
    return problems


def assert_flow_ui_publishable(document: FlowUIDocument, limits: FlowUILimits) -> None:
    problems = flow_ui_problems(document, limits)
    if problems:
        first = problems[0]
        location = ", ".join(part for part in (first.page_id, first.block_id) if part is not None)
        raise ValueError(
            f"Flow UI: {first.message} ({location or 'document'}); total problems: {len(problems)}"
        )


__all__ = [
    "RESERVED_WRITE_FIELDS",
    "FlowUILimits",
    "FlowUIProblem",
    "assert_flow_ui_publishable",
    "flow_ui_problems",
]
