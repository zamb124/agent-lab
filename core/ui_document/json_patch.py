"""Патчи RFC 6902 над ``JsonObject`` для Flow UI: diff двух проекций и их применение.

Чистый wire-уровень: операции — ``JsonPatchOperation`` из ``protocol``,
сам ExecutionState здесь не нужен.
"""

from __future__ import annotations

from core.types import JsonObject
from core.ui_document.protocol import JsonPatchOperation


def pointer_segment(segment: str) -> str:
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
            out.append(JsonPatchOperation(op="remove", path=f"{prefix}/{pointer_segment(key)}"))
    for key, value in after.items():
        path = f"{prefix}/{pointer_segment(key)}"
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


def pointer_segments(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError(f"json patch: pointer must start with '/': {pointer!r}")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]


def apply_json_patch(target: JsonObject, operations: list[JsonPatchOperation]) -> JsonObject:
    """Применяет add/replace/remove к копии ``target``; чужой путь — ошибка."""

    patched: JsonObject = dict(target)
    for operation in operations:
        segments = pointer_segments(operation.path)
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


__all__ = [
    "apply_json_patch",
    "json_patch_operations",
]
