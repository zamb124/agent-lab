"""
Сбор файлов из конфигов нод графа в state.files (старт новой сессии).
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List


def validate_node_files_list(
    files: Any,
    *,
    node_id: str,
) -> None:
    """
    Zero-guess: files — список объектов с обязательными строковыми name и path.
    """
    if files is None:
        return
    if not isinstance(files, list):
        raise ValueError(f"Нода '{node_id}': files должен быть списком")
    for idx, item in enumerate(files):
        if not isinstance(item, dict):
            raise ValueError(
                f"Нода '{node_id}': files[{idx}] должен быть объектом с полями name и path"
            )
        name = item.get("name")
        path = item.get("path")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"Нода '{node_id}': files[{idx}].name — непустая строка обязательна"
            )
        if not isinstance(path, str) or not path.strip():
            raise ValueError(
                f"Нода '{node_id}': files[{idx}].path — непустая строка обязательна"
            )


def collect_flow_node_files(nodes: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Объединяет поля files всех нод эффективного графа (порядок: обход по ключам словаря
    nodes в стабильном для JSON порядке — как в объекте; в Python 3.7+ dict сохраняет вставку).

    Каждая запись копируется (shallow), чтобы мутации state не меняли конфиг в памяти.
    """
    if not nodes:
        return []
    merged: List[Dict[str, Any]] = []
    for node_id, cfg in nodes.items():
        if not isinstance(cfg, dict):
            continue
        raw = cfg.get("files")
        if not raw:
            continue
        validate_node_files_list(raw, node_id=node_id)
        for item in raw:
            merged.append(copy.copy(item))
    return merged
