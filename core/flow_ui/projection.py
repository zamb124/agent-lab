"""Проекция ExecutionState для клиента Flow UI и патчи RFC 6902.

Клиент получает ровно те пути state, на которые ссылается интерфейс:
``{path}`` в текстовых свойствах, ``field`` input-блоков, ``visible_when.path``,
привязки данных, ``fields`` и ``data-bind``/``data-show`` блоков ``html``.
Frozen-поля в проекцию не попадают никогда.
"""

from __future__ import annotations

import types
from collections.abc import Iterable, Sequence
from typing import Annotated, cast, get_args, get_origin

from pydantic import BaseModel

from core.flow_ui.document import (
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
from core.flow_ui.html_bindings import html_bound_paths
from core.flow_ui.protocol import JsonPatchOperation
from core.state.mutation_policy import FROZEN_STATE_FIELDS
from core.types import JsonObject, JsonValue
from core.variables.template_scan import scan_prompt_template


def template_paths(text: str) -> list[str]:
    """Пути переменных текстового шаблона в порядке появления."""

    return [ref.name for ref in scan_prompt_template(text).refs]


type FlowUIFieldMarker = FlowUITemplateText | FlowUIStatePathMarker | FlowUIImageUrlMarker
type FlowUIAnnotation = type | types.GenericAlias | types.UnionType | None
type FlowUIAnnotationArg = FlowUIAnnotation | FlowUIFieldMarker
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


def _annotation_args(annotation: FlowUIAnnotationArg) -> tuple[FlowUIAnnotationArg, ...]:
    return cast(tuple[FlowUIAnnotationArg, ...], get_args(annotation))


def _has_markers(metadata: Sequence[FlowUIAnnotationArg]) -> tuple[bool, bool]:
    template = any(isinstance(meta, FlowUITemplateText) for meta in metadata)
    state_path = any(isinstance(meta, FlowUIStatePathMarker) for meta in metadata)
    return template, state_path


def _annotation_markers(annotation: FlowUIAnnotationArg) -> tuple[bool, bool]:
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


def _pointer_segment(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")


def json_patch_operations(before: JsonObject, after: JsonObject) -> list[JsonPatchOperation]:
    """RFC 6902 diff двух проекций: объекты — по ключам, списки и скаляры — целиком."""

    operations: list[JsonPatchOperation] = []
    _diff_objects(before, after, "", operations)
    return operations


def _diff_objects(
    before: JsonObject, after: JsonObject, prefix: str, out: list[JsonPatchOperation]
) -> None:
    for key in before:
        if key not in after:
            out.append(JsonPatchOperation(op="remove", path=f"{prefix}/{_pointer_segment(key)}"))
    for key, value in after.items():
        path = f"{prefix}/{_pointer_segment(key)}"
        if key not in before:
            out.append(JsonPatchOperation(op="add", path=path, value=value))
            continue
        previous = before[key]
        if previous == value:
            continue
        if isinstance(previous, dict) and isinstance(value, dict):
            _diff_objects(previous, value, path, out)
            continue
        out.append(JsonPatchOperation(op="replace", path=path, value=value))


def _pointer_segments(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError(f"json patch: pointer must start with '/': {pointer!r}")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]


def apply_json_patch(target: JsonObject, operations: list[JsonPatchOperation]) -> JsonObject:
    """Применяет add/replace/remove к копии ``target``; чужой путь — ошибка."""

    patched: JsonObject = dict(target)
    for operation in operations:
        segments = _pointer_segments(operation.path)
        if not segments:
            if operation.op == "remove":
                raise ValueError("json patch: cannot remove document root")
            if not isinstance(operation.value, dict):
                raise ValueError("json patch: root value must be an object")
            patched = dict(operation.value)
            continue
        parent: JsonObject = patched
        for segment in segments[:-1]:
            child = parent.get(segment)
            if not isinstance(child, dict):
                if operation.op == "remove":
                    raise ValueError(f"json patch: path {operation.path!r} does not exist")
                child = {}
                parent[segment] = child
            else:
                child = dict(child)
                parent[segment] = child
            parent = child
        leaf = segments[-1]
        if operation.op == "remove":
            if leaf not in parent:
                raise ValueError(f"json patch: path {operation.path!r} does not exist")
            del parent[leaf]
        else:
            parent[leaf] = operation.value
    return patched


def validate_redacted_paths(pointers: list[str]) -> list[str]:
    """JSON Pointers полей state для share-редакции: непустые, уникальные, вне frozen-корней."""

    validated: list[str] = []
    for pointer in pointers:
        segments = _pointer_segments(pointer.strip())
        if not segments or segments[0] == "":
            raise ValueError(f"redacted path must point to a state field: {pointer!r}")
        if segments[0] in FROZEN_STATE_FIELDS:
            raise ValueError(f"redacted path cannot target a system field: {pointer!r}")
        normalized = "/" + "/".join(_pointer_segment(segment) for segment in segments)
        if normalized not in validated:
            validated.append(normalized)
    return validated


def redact_state(projection: JsonObject, redacted_paths: list[str]) -> JsonObject:
    """Копия проекции без значений по ``redacted_paths``; отсутствующие пути пропускаются."""

    redacted: JsonObject = dict(projection)
    for pointer in redacted_paths:
        segments = _pointer_segments(pointer)
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
        pointer = "/" + "/".join(_pointer_segment(segment) for segment in field.split("."))
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
    "apply_json_patch",
    "assert_fields_outside_redacted",
    "block_paths",
    "block_templates",
    "json_patch_operations",
    "project_state",
    "redact_state",
    "referenced_paths",
    "template_paths",
    "validate_redacted_paths",
]
