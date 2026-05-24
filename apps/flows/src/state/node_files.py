"""
Сбор файлов из конфигов нод графа в state.files (старт новой сессии).
"""

from __future__ import annotations

from collections.abc import Mapping

from core.files.file_ref import FileRef
from core.types import JsonObject, require_json_array, require_json_object


def validate_node_files_list(
    files: object,
    *,
    node_id: str,
) -> None:
    """
    Zero-guess: files — список канонических FileRef.
    """
    if files is None:
        return
    try:
        file_items = require_json_array(files, f"nodes.{node_id}.files")
    except ValueError as exc:
        raise ValueError(f"Нода '{node_id}': files должен быть списком") from exc
    for idx, raw_item in enumerate(file_items):
        item = require_json_object(raw_item, f"nodes.{node_id}.files[{idx}]")
        try:
            _ = FileRef.model_validate(item)
        except ValueError as exc:
            raise ValueError(
                f"Нода '{node_id}': files[{idx}] не является FileRef: {exc}"
            ) from exc


def collect_flow_node_files(nodes: Mapping[str, JsonObject]) -> list[FileRef]:
    """
    Объединяет поля files всех нод эффективного графа (порядок: обход по ключам словаря
    nodes в стабильном для JSON порядке — как в объекте; в Python 3.7+ dict сохраняет вставку).

    Каждая запись копируется (shallow), чтобы мутации state не меняли конфиг в памяти.
    """
    if not nodes:
        return []
    merged: list[FileRef] = []
    for node_id, cfg_obj in nodes.items():
        raw = cfg_obj.get("files")
        if raw is None:
            continue
        validate_node_files_list(raw, node_id=node_id)
        file_items = require_json_array(raw, f"nodes.{node_id}.files")
        for idx, item in enumerate(file_items):
            file_obj = require_json_object(item, f"nodes.{node_id}.files[{idx}]")
            merged.append(FileRef.model_validate(file_obj))
    return merged
