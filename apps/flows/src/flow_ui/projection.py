"""Проекция ExecutionState для клиента Flow UI.

Клиент получает ровно те пути state, на которые ссылается интерфейс:
``{path}`` в текстовых свойствах, ``field`` input-блоков, ``visible_when.path``,
привязки данных, ``fields`` и ``data-bind``/``data-show`` блоков ``html``.
Frozen-поля в проекцию не попадают никогда. Патчи RFC 6902 — ``core/ui_document/json_patch``.
"""

from __future__ import annotations

import types
from collections.abc import Iterable, Sequence
from typing import Annotated, TypeVar, cast, get_args, get_origin

from pydantic import BaseModel
from typing_extensions import TypeForm

from apps.flows.src.flow_ui.html_bindings import html_bound_paths
from apps.flows.src.state.mutation_policy import FROZEN_STATE_FIELDS
from core.types import JsonObject, JsonValue
from core.ui_document.document import (
    FlowUIBlockBase,
    FlowUIBlockModel,
    FlowUIDataTable,
    FlowUIDocument,
    FlowUIFileCard,
    FlowUIHtml,
    FlowUIImageUrlMarker,
    FlowUIStatePathMarker,
    FlowUITemplateText,
    iter_blocks,
)
from core.ui_document.json_patch import pointer_segment, pointer_segments
from core.variables.template_scan import scan_prompt_template


def template_paths(text: str) -> list[str]:
    """Пути переменных текстового шаблона в порядке появления."""

    return [ref.name for ref in scan_prompt_template(text).refs]


type FlowUIFieldMarker = FlowUITemplateText | FlowUIStatePathMarker | FlowUIImageUrlMarker
type FlowUIAnnotation = type | types.GenericAlias | types.UnionType | None
type FlowUIAnnotationArg = FlowUIAnnotation | FlowUIFieldMarker
_FieldAnnotation = TypeVar("_FieldAnnotation")
type FlowUIFieldValue = (
    str
    | int
    | float
    | bool
    | None
    | FlowUIBlockBase
    | BaseModel
    | JsonValue
    | list[FlowUIFieldValue]
)


def _annotation_args(
    annotation: TypeForm[_FieldAnnotation] | FlowUIAnnotationArg,
) -> tuple[FlowUIAnnotationArg, ...]:
    return cast(tuple[FlowUIAnnotationArg, ...], get_args(annotation))


def _has_markers(metadata: Sequence[FlowUIAnnotationArg]) -> tuple[bool, bool]:
    template = any(isinstance(meta, FlowUITemplateText) for meta in metadata)
    state_path = any(isinstance(meta, FlowUIStatePathMarker) for meta in metadata)
    return template, state_path


def _annotation_markers(
    annotation: TypeForm[_FieldAnnotation] | FlowUIAnnotationArg,
) -> tuple[bool, bool]:
    origin = get_origin(annotation)
    args = _annotation_args(annotation)
    if origin is Annotated:
        template, state_path = _has_markers(args[1:])
        inner_template, inner_path = _annotation_markers(args[0])
        return template or inner_template, state_path or inner_path
    if origin in (list, types.UnionType):
        template = False
        state_path = False
        for arg in args:
            inner_template, inner_path = _annotation_markers(arg)
            template = template or inner_template
            state_path = state_path or inner_path
        return template, state_path
    return False, False


class _BlockReferences:
    """Строки одного блока, размеченные маркерами грамматики: пути state и текстовые шаблоны."""

    def __init__(self) -> None:
        self.paths: list[str] = []
        self.templates: list[str] = []


def _collect_from_value(
    value: FlowUIFieldValue, *, template: bool, state_path: bool, out: _BlockReferences
) -> None:
    if isinstance(value, str):
        if state_path:
            out.paths.append(value)
        elif template:
            if value != "":
                out.templates.append(value)
            out.paths.extend(template_paths(value))
        return
    if isinstance(value, FlowUIBlockBase):
        # Вложенные блоки контейнеров обходит вызывающий через iter_blocks: у каждого свои пути
        return
    if isinstance(value, BaseModel):
        _collect_from_model(value, out)
        return
    if isinstance(value, list):
        for item in value:
            _collect_from_value(item, template=template, state_path=state_path, out=out)


def _collect_from_model(model: BaseModel, out: _BlockReferences) -> None:
    for name, info in type(model).model_fields.items():
        template, state_path = _has_markers(info.metadata)
        inner_template, inner_path = _annotation_markers(info.annotation)
        _collect_from_value(
            cast(FlowUIFieldValue, getattr(model, name)),
            template=template or inner_template,
            state_path=state_path or inner_path,
            out=out,
        )


def block_templates(block: FlowUIBlockModel) -> list[str]:
    """Непустые текстовые шаблоны одного блока (без вложенных) в порядке полей грамматики."""

    references = _BlockReferences()
    _collect_from_model(block, references)
    return references.templates


def block_paths(block: FlowUIBlockModel) -> list[str]:
    """Все пути state, на которые ссылается один блок (без вложенных)."""

    references = _BlockReferences()
    _collect_from_model(block, references)
    collected = references.paths
    if isinstance(block, FlowUIHtml):
        collected.extend(html_bound_paths(block.source))
    if isinstance(block, FlowUIFileCard | FlowUIDataTable) and block.file_id != "":
        # FileRef по file_id клиент находит в проекции state.files
        collected.append("files")
    ordered: list[str] = []
    for path in collected:
        if path not in ordered:
            ordered.append(path)
    return ordered


def referenced_paths(
    document: FlowUIDocument,
    ui_slots: dict[str, list[FlowUIBlockModel]],
) -> frozenset[str]:
    """Пути state, видимые клиенту: документ плюс блоки, отрендеренные агентом."""

    collected: set[str] = set()
    for block in document.blocks():
        collected.update(block_paths(block))
    for blocks in ui_slots.values():
        for block in iter_blocks(blocks):
            collected.update(block_paths(block))
    return frozenset(collected)


def _resolve(payload: JsonObject, segments: list[str]) -> tuple[bool, JsonValue, int]:
    """Значение по сегментам; список останавливает спуск и отдаётся целиком."""

    current: JsonValue = payload
    for index, segment in enumerate(segments):
        if isinstance(current, list):
            return True, current, index
        if not isinstance(current, dict) or segment not in current:
            return False, None, index
        current = current[segment]
    return True, current, len(segments)


def _assign(target: JsonObject, segments: list[str], value: JsonValue) -> None:
    current = target
    for segment in segments[:-1]:
        child = current.get(segment)
        if not isinstance(child, dict):
            child = {}
            current[segment] = child
        current = child
    current[segments[-1]] = value


def project_state(payload: JsonObject, paths: frozenset[str] | set[str]) -> JsonObject:
    """Подмножество ``payload`` по путям; отсутствующие пути пропускаются."""

    projection: JsonObject = {}
    included: list[list[str]] = []
    for path in sorted(paths, key=lambda item: (item.count("."), item)):
        segments = path.split(".")
        if segments[0] in FROZEN_STATE_FIELDS:
            continue
        found, value, depth = _resolve(payload, segments)
        if not found:
            continue
        effective = segments[:depth] if depth > 0 else segments
        if any(effective[: len(prefix)] == prefix for prefix in included):
            continue
        included.append(effective)
        _assign(projection, effective, value)
    return projection


def validate_redacted_paths(pointers: list[str]) -> list[str]:
    """JSON Pointers полей state для share-редакции: непустые, уникальные, вне frozen-корней."""

    validated: list[str] = []
    for pointer in pointers:
        segments = pointer_segments(pointer.strip())
        if not segments or segments[0] == "":
            raise ValueError(f"redacted path must point to a state field: {pointer!r}")
        if segments[0] in FROZEN_STATE_FIELDS:
            raise ValueError(f"redacted path cannot target a system field: {pointer!r}")
        normalized = "/" + "/".join(pointer_segment(segment) for segment in segments)
        if normalized not in validated:
            validated.append(normalized)
    return validated


def redact_state(projection: JsonObject, redacted_paths: list[str]) -> JsonObject:
    """Копия проекции без значений по ``redacted_paths``; отсутствующие пути пропускаются."""

    redacted: JsonObject = dict(projection)
    for pointer in redacted_paths:
        segments = pointer_segments(pointer)
        parent: JsonObject = redacted
        missing = False
        for segment in segments[:-1]:
            child = parent.get(segment)
            if not isinstance(child, dict):
                missing = True
                break
            child = dict(child)
            parent[segment] = child
            parent = child
        if missing or segments[-1] not in parent:
            continue
        del parent[segments[-1]]
    return redacted


def assert_fields_outside_redacted(fields: Iterable[str], redacted_paths: list[str]) -> None:
    """Editor-посетитель share не пишет в скрытые от него поля: ни в путь, ни внутрь, ни поверх."""

    for field in fields:
        pointer = "/" + "/".join(pointer_segment(segment) for segment in field.split("."))
        for redacted in redacted_paths:
            if (
                pointer == redacted
                or pointer.startswith(redacted + "/")
                or redacted.startswith(pointer + "/")
            ):
                raise PermissionError(
                    f"Flow UI share grant forbids client writes to redacted path {redacted!r}"
                )


__all__ = [
    "assert_fields_outside_redacted",
    "block_paths",
    "block_templates",
    "project_state",
    "redact_state",
    "referenced_paths",
    "template_paths",
    "validate_redacted_paths",
]
