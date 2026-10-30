"""
Тулы интерфейса для llm_node: ``ui_render``, ``ui_navigate``, ``state_set``.

Аргументы ``ui_render`` — та же Pydantic-грамматика блоков, что и у документа
интерфейса, поэтому невалидный UI отклоняется валидацией тула. Данные экрана
LLM меняет через ``state_set`` — как любые данные flow; отдельных UI-операций
над данными нет.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.flow_ui.runtime import (
    apply_ui_navigate,
    apply_ui_render,
    assert_known_page,
    assert_known_slot,
)
from apps.flows.src.runtime.flow_interface_context import current_flow_interface
from apps.flows.src.state.state_path import assign_state_path
from apps.flows.src.tools.decorator import tool
from core.types import JsonObject, JsonValue
from core.ui_document.document import FlowUIBlock, FlowUIBlockId, FlowUIPageId
from core.ui_document.protocol import FlowUINavigate, FlowUIRender

if TYPE_CHECKING:
    from apps.flows.src.state import ExecutionState


class UIRenderArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    slot_id: FlowUIBlockId = Field(
        ...,
        description=(
            "Куда показать блоки: block_id блока slot из интерфейса (содержимое slot заменяется) "
            "или 'conversation' (карточка добавляется в ленту)."
        ),
    )
    blocks: list[FlowUIBlock] = Field(
        ...,
        min_length=1,
        description=(
            "Блоки интерфейса. Текст блоков поддерживает подстановки {path} из state; "
            "input-блоки пишут значение в state по field."
        ),
    )


class UINavigateArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    page_id: FlowUIPageId = Field(..., description="page_id страницы интерфейса.")


class StateSetArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    path: str = Field(
        ...,
        min_length=1,
        description="Dotted-путь поля state: 'email' или 'order.customer.email'.",
    )
    value: JsonValue = Field(..., description="Новое значение (любой JSON).")


@tool(
    name="ui_render",
    description=(
        "Показывает блоки интерфейса пользователю: в slot страницы (заменяя его содержимое) "
        "или карточкой в ленте conversation. Используй для таблиц, метрик, форм, кнопок и "
        "других визуальных ответов вместо длинного текста."
    ),
    tags=["flows"],
    parameters_model=UIRenderArgs,
)
async def ui_render(
    slot_id: str,
    blocks: list[JsonValue],
    *,
    state: "ExecutionState",
) -> JsonObject:
    render = FlowUIRender.model_validate({"slot_id": slot_id, "blocks": blocks})
    assert_known_slot(current_flow_interface(), render.slot_id)
    apply_ui_render(state, render)
    return {
        "slot_id": render.slot_id,
        "block_ids": [block.block_id for block in render.blocks],
    }


@tool(
    name="ui_navigate",
    description="Переключает пользователя на другую страницу интерфейса flow.",
    tags=["flows"],
    parameters_model=UINavigateArgs,
)
async def ui_navigate(page_id: str, *, state: "ExecutionState") -> JsonObject:
    navigate = FlowUINavigate(page_id=page_id)
    assert_known_page(current_flow_interface(), navigate.page_id)
    apply_ui_navigate(state, navigate)
    return {"page_id": navigate.page_id}


@tool(
    name="state_set",
    description=(
        "Записывает значение в поле state по dotted-пути. Интерфейс показывает поля state "
        "через {path}, поэтому так меняются данные на экране."
    ),
    tags=["flows"],
    parameters_model=StateSetArgs,
)
async def state_set(path: str, value: JsonValue, *, state: "ExecutionState") -> JsonObject:
    assign_state_path(state, path, value)
    return {"path": path, "value": value}
