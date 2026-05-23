"""
Сбор файлов из конфигов нод графа в state.files (старт новой сессии).
"""

from __future__ import annotations

from collections.abc import Mapping

from core.types import JsonObject, require_json_array, require_json_object


def validate_node_files_list(
    files: object,
    *,
    node_id: str,
) -> None:
    """
    Zero-guess: files — список объектов с обязательными строковыми original_name и url.
    """
    if files is None:
        return
    file_items = require_json_array(files, f"nodes.{node_id}.files")
    for idx, raw_item in enumerate(file_items):
        item = require_json_object(raw_item, f"nodes.{node_id}.files[{idx}]")
        original_name = item.get("original_name")
        url = item.get("url")
        if not isinstance(original_name, str) or not original_name.strip():
            raise ValueError(
                f"Нода '{node_id}': files[{idx}].original_name — непустая строка обязательна"
            )
        if not isinstance(url, str) or not url.strip():
            raise ValueError(
                f"Нода '{node_id}': files[{idx}].url — непустая строка обязательна"
            )


def collect_flow_node_files(nodes: Mapping[str, JsonObject]) -> list[JsonObject]:
    """
    Объединяет поля files всех нод эффективного графа (порядок: обход по ключам словаря
    nodes в стабильном для JSON порядке — как в объекте; в Python 3.7+ dict сохраняет вставку).

    Каждая запись копируется (shallow), чтобы мутации state не меняли конфиг в памяти.
    """
    if not nodes:
        return []
    merged: list[JsonObject] = []
    for node_id, cfg_obj in nodes.items():
        raw = cfg_obj.get("files")
        if raw is None:
            continue
        validate_node_files_list(raw, node_id=node_id)
        file_items = require_json_array(raw, f"nodes.{node_id}.files")
        for idx, item in enumerate(file_items):
            merged.append(require_json_object(item, f"nodes.{node_id}.files[{idx}]"))
    return merged
