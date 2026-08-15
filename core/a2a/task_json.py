"""Извлечение текста/data из ProtoJSON Task (A2A 1.0, без Part.kind)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

from core.types import JsonObject, require_json_object

_ROLE_AGENT = "ROLE_AGENT"


def _part_text(part: JsonObject) -> str | None:
    text_value = part.get("text")
    if isinstance(text_value, str) and text_value.strip():
        return text_value.strip()
    return None


def iter_json_parts(parts_value: object) -> Iterator[JsonObject]:
    """Итерирует Part dict из ProtoJSON (presence text|raw|url|data)."""
    if not isinstance(parts_value, list):
        return
    for part_value in cast(list[object], parts_value):
        if not isinstance(part_value, dict):
            continue
        # isinstance(dict) сужает до dict[Unknown, Unknown] — снова object для boundary.
        yield require_json_object(cast(object, part_value), "a2a.part")


def _parts_text_chunks(parts_value: object) -> list[str]:
    chunks: list[str] = []
    for part in iter_json_parts(parts_value):
        text = _part_text(part)
        if text is not None:
            chunks.append(text)
    return chunks


def _message_text(message: JsonObject) -> str | None:
    chunks = _parts_text_chunks(message.get("parts"))
    if not chunks:
        return None
    return "\n".join(chunks)


def part_json_has_text(part: JsonObject) -> bool:
    return _part_text(part) is not None


def part_json_has_data(part: JsonObject) -> bool:
    return "data" in part and part.get("data") is not None


def extract_text_from_parts_json(parts_value: object) -> str | None:
    chunks = _parts_text_chunks(parts_value)
    if not chunks:
        return None
    return "\n".join(chunks)


def extract_text_from_task_json(task_payload: JsonObject) -> str:
    """
    Текст ответа Task из ProtoJSON.

    Порядок: status.message (текущий ход) → history ROLE_AGENT с конца
    → artifacts text → data.res.

    History на Task замораживается при ensure (может содержать прошлые ходы
    той же session). Status.message — сообщение текущего состояния Task.
    """
    status_value = task_payload.get("status")
    if isinstance(status_value, dict):
        status_object = require_json_object(status_value, "a2a.task.status")
        message_value = status_object.get("message")
        if isinstance(message_value, dict):
            message = require_json_object(message_value, "a2a.task.status.message")
            text = _message_text(message)
            if text is not None:
                return text

    history_raw = task_payload.get("history")
    if isinstance(history_raw, list):
        for message_item in reversed(history_raw):
            if not isinstance(message_item, dict):
                continue
            message = require_json_object(message_item, "a2a.task.history.message")
            if message.get("role") != _ROLE_AGENT:
                continue
            text = _message_text(message)
            if text is not None:
                return text

    artifacts_value = task_payload.get("artifacts")
    if isinstance(artifacts_value, list):
        chunks: list[str] = []
        for artifact_value in artifacts_value:
            if not isinstance(artifact_value, dict):
                continue
            artifact = require_json_object(artifact_value, "a2a.task.artifact")
            for part in iter_json_parts(artifact.get("parts")):
                text = _part_text(part)
                if text is not None:
                    chunks.append(text)
                    continue
                data_value = part.get("data")
                if not isinstance(data_value, dict):
                    continue
                data_obj = require_json_object(data_value, "a2a.part.data")
                res_value = data_obj.get("res")
                if isinstance(res_value, str) and res_value.strip():
                    chunks.append(res_value.strip())
        if chunks:
            return "\n".join(chunks)

    raise ValueError("A2A Task JSON не содержит текстового ответа")


def iter_artifact_parts_from_task_json(task_payload: JsonObject) -> Iterator[JsonObject]:
    """Все Part из artifacts Task (ProtoJSON)."""
    artifacts_value = task_payload.get("artifacts")
    if not isinstance(artifacts_value, list):
        return
    for artifact_value in artifacts_value:
        if not isinstance(artifact_value, dict):
            continue
        artifact = require_json_object(artifact_value, "a2a.task.artifact")
        yield from iter_json_parts(artifact.get("parts"))


def iter_history_parts_from_task_json(task_payload: JsonObject) -> Iterator[JsonObject]:
    """Все Part из history messages Task (ProtoJSON)."""
    history_raw = task_payload.get("history")
    if not isinstance(history_raw, list):
        return
    for message_item in history_raw:
        if not isinstance(message_item, dict):
            continue
        message = require_json_object(message_item, "a2a.task.history.message")
        yield from iter_json_parts(message.get("parts"))


__all__ = [
    "extract_text_from_parts_json",
    "extract_text_from_task_json",
    "iter_artifact_parts_from_task_json",
    "iter_history_parts_from_task_json",
    "iter_json_parts",
    "part_json_has_data",
    "part_json_has_text",
]
