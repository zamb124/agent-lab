"""Приём ``ui-action``: значения input-блоков становятся обычными полями ExecutionState.

Сервер принимает запись только в поля, объявленные input-блоками документа или
отрендеренные агентом (``ui_slots``); значение проверяется по типу блока. Кроме
полей ход получает ``ui_action`` (событие) и ``content`` (Markdown-проекция с
подписями блоков); файлы ``file_upload`` канал кладёт в ``state.files``.
"""

from __future__ import annotations

from typing import final

from a2a.types import Message

from apps.flows.src.flow_ui.projection import template_paths
from apps.flows.src.state.execution_state import ExecutionState
from apps.flows.src.state.state_path import assign_state_path
from core.a2a.codec import get_part_data, part_has_data, part_has_text
from core.files.file_ref import FileRef
from core.types import JsonValue
from core.ui_document.document import (
    FlowUIBlockModel,
    FlowUICheckbox,
    FlowUIDateInput,
    FlowUIDateTimeInput,
    FlowUIDocument,
    FlowUIFileUpload,
    FlowUIHtml,
    FlowUIInputBase,
    FlowUINumberInput,
    FlowUIPage,
    FlowUISelect,
    FlowUISlider,
    FlowUISwitch,
    FlowUITextInput,
    FlowUIVoiceInput,
    iter_blocks,
)
from core.ui_document.protocol import FLOW_UI_ACTION_MEDIA_TYPE, FlowUIActionMessage

FlowUIWritableBlock = FlowUIInputBase | FlowUIHtml


def ui_action_from_message(message: Message) -> FlowUIActionMessage | None:
    """Единственный ``data`` Part с mediaType ui-action; текстовый ход возвращает None."""
    actions = [
        part
        for part in message.parts
        if part_has_data(part) and part.media_type == FLOW_UI_ACTION_MEDIA_TYPE
    ]
    if not actions:
        return None
    if len(actions) > 1:
        raise ValueError("ui-action message must contain exactly one action Part")
    if any(part_has_text(part) and part.text.strip() != "" for part in message.parts):
        raise ValueError("ui-action message cannot combine action and text Parts")
    return FlowUIActionMessage.model_validate(get_part_data(actions[0]))


def _writable_blocks(
    document: FlowUIDocument, ui_slots: dict[str, list[FlowUIBlockModel]]
) -> dict[str, FlowUIWritableBlock]:
    writable: dict[str, FlowUIWritableBlock] = {}
    rendered: list[FlowUIBlockModel] = []
    for blocks in ui_slots.values():
        rendered.extend(iter_blocks(blocks))
    for block in [*document.blocks(), *rendered]:
        if isinstance(block, FlowUIInputBase):
            _ = writable.setdefault(block.field, block)
        elif isinstance(block, FlowUIHtml) and block.field is not None:
            _ = writable.setdefault(block.field, block)
    return writable


def _page_of(document: FlowUIDocument, block_id: str) -> FlowUIPage | None:
    for page in document.pages:
        if any(block.block_id == block_id for block in iter_blocks(page.blocks)):
            return page
    return None


def _is_empty(value: JsonValue) -> bool:
    return value is None or value == "" or value == []


def validate_field_value(block: FlowUIWritableBlock, value: JsonValue) -> JsonValue:
    """Значение по типу блока; чужой тип — ошибка хода."""

    label = f"{type(block).__name__} {block.block_id!r}"
    if isinstance(
        block, FlowUITextInput | FlowUIDateInput | FlowUIDateTimeInput | FlowUIVoiceInput
    ):
        if not isinstance(value, str):
            raise ValueError(f"{label}: expected string")
        return value
    if isinstance(block, FlowUINumberInput | FlowUISlider):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{label}: expected number")
        return value
    if isinstance(block, FlowUICheckbox | FlowUISwitch):
        if not isinstance(value, bool):
            raise ValueError(f"{label}: expected boolean")
        return value
    if isinstance(block, FlowUISelect):
        allowed = {option.value for option in block.options}
        if block.multiple:
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"{label}: expected list of option values")
            unknown = [item for item in value if item not in allowed]
        else:
            if not isinstance(value, str):
                raise ValueError(f"{label}: expected option value")
            unknown = [] if value in allowed else [value]
        if unknown:
            raise ValueError(f"{label}: unknown option {unknown[0]!r}")
        return value
    if isinstance(block, FlowUIFileUpload):
        if not isinstance(value, list):
            raise ValueError(f"{label}: expected list of files")
        return [FileRef.model_validate(item).model_dump(mode="json") for item in value]
    return value


def _item_text(item: JsonValue) -> str:
    if isinstance(item, dict):
        original_name = item.get("original_name")
        if isinstance(original_name, str):
            return original_name
    return str(item)


def render_ui_action_markdown(
    message: FlowUIActionMessage,
    blocks_by_field: dict[str, FlowUIWritableBlock],
) -> str:
    """Markdown-проекция хода: действие и значения с подписями блоков в порядке интерфейса."""

    lines = [f"Действие: {message.action}"]
    for field, block in blocks_by_field.items():
        if field not in message.fields:
            continue
        value = message.fields[field]
        label = block.label if isinstance(block, FlowUIInputBase) and block.label else field
        if template_paths(label):
            label = field
        if isinstance(value, list):
            rendered = ", ".join(_item_text(item) for item in value)
        elif isinstance(value, bool):
            rendered = "да" if value else "нет"
        else:
            rendered = "" if value is None else str(value)
        lines.append(f"- {label}: {rendered}")
    return "\n".join(lines)


@final
class FlowUIValidatedAction:
    """Проверенный ход: значения по типам блоков и Markdown-проекция для ``content``."""

    __slots__ = ("content", "fields", "writable")

    def __init__(
        self,
        *,
        fields: dict[str, JsonValue],
        writable: dict[str, FlowUIWritableBlock],
        content: str,
    ) -> None:
        self.fields: dict[str, JsonValue] = fields
        self.writable: dict[str, FlowUIWritableBlock] = writable
        self.content: str = content


def validate_flow_ui_action(
    message: FlowUIActionMessage,
    document: FlowUIDocument,
    ui_slots: dict[str, list[FlowUIBlockModel]],
) -> FlowUIValidatedAction:
    """Проверка хода на входе канала: неизвестные поля, required страницы источника, типы значений."""

    writable = _writable_blocks(document, ui_slots)
    unknown = [field for field in message.fields if field not in writable]
    if unknown:
        raise ValueError(f"ui-action: field {unknown[0]!r} is not an input of this interface")
    page = _page_of(document, message.source)
    if page is not None:
        for block in iter_blocks(page.blocks):
            if isinstance(block, FlowUIInputBase) and block.required:
                if block.field not in message.fields or _is_empty(message.fields[block.field]):
                    raise ValueError(f"ui-action: required field {block.field!r} is empty")
    fields = {
        field: validate_field_value(writable[field], value)
        for field, value in message.fields.items()
    }
    return FlowUIValidatedAction(
        fields=fields, writable=writable, content=render_ui_action_markdown(message, writable)
    )


def apply_flow_ui_action(
    state: ExecutionState,
    message: FlowUIActionMessage,
    document: FlowUIDocument,
) -> list[FileRef]:
    """Записывает ``fields`` в state, ставит ``ui_action`` и ``content``; возвращает файлы ``file_upload``."""

    validated = validate_flow_ui_action(message, document, state.ui_slots)
    files: list[FileRef] = []
    for field, value in validated.fields.items():
        assign_state_path(state, field, value)
        if isinstance(validated.writable[field], FlowUIFileUpload) and isinstance(value, list):
            files.extend(FileRef.model_validate(item) for item in value)
    state.ui_action = message.to_state_action()
    state.content = validated.content
    return files


__all__ = [
    "FlowUIValidatedAction",
    "FlowUIWritableBlock",
    "apply_flow_ui_action",
    "render_ui_action_markdown",
    "ui_action_from_message",
    "validate_field_value",
    "validate_flow_ui_action",
]
