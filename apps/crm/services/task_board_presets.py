"""
Резолвер колонок доски задач (канбан) по настройкам пространства.

Ключ доски: task | task:<entity_subtype>. Единая точка дефолтных стадий и резолва пресетов.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence

from core.models.identity_models import BoardStage, NamespaceCRMSettings, TaskBoardPreset

TASK_ENTITY_TYPE = "task"


def task_board_key(entity_type: str, entity_subtype: Optional[str]) -> str:
    et = (entity_type or "").strip()
    if et != TASK_ENTITY_TYPE:
        raise ValueError(f"task_board_key: ожидался entity_type={TASK_ENTITY_TYPE!r}, получено {et!r}")
    sub = (entity_subtype or "").strip()
    if sub:
        return f"{TASK_ENTITY_TYPE}:{sub}"
    return TASK_ENTITY_TYPE


def default_task_board_stages() -> tuple[BoardStage, ...]:
    """Системные стадии, если для ключа нет пресета в namespace."""
    return (
        BoardStage(id="todo", label="К выполнению"),
        BoardStage(id="in_progress", label="В работе"),
        BoardStage(id="done", label="Готово"),
    )


def resolve_task_board_stages(
    crm: NamespaceCRMSettings,
    board_key: str,
) -> list[BoardStage]:
    if not board_key or not board_key.strip():
        raise ValueError("resolve_task_board_stages: пустой board_key")
    k = board_key.strip()
    preset = crm.pipeline_stage_presets.get(k)
    if preset is not None:
        return list(preset.stages)
    return list(default_task_board_stages())


def resolve_allowed_task_status_ids(
    crm: NamespaceCRMSettings,
    board_key: str,
) -> set[str]:
    return {s.id for s in resolve_task_board_stages(crm, board_key)}


def build_task_board_editor_boards(
    *,
    allowed_type_ids: Sequence[str],
    entity_types: Sequence[Any],
    crm: NamespaceCRMSettings,
) -> list[dict[str, Any]]:
    """
    Подготовка данных для UI редактора стадий: только через сервер.

    entity_types: объекты с полями type_id, name, parent_type_id (как ORM EntityType).
    """
    allowed = set(allowed_type_ids)
    by_id: dict[str, Any] = {}
    for t in entity_types:
        tid = getattr(t, "type_id", None)
        if isinstance(tid, str) and tid:
            by_id[tid] = t

    boards: list[dict[str, Any]] = []
    if "task" in allowed:
        key = task_board_key(TASK_ENTITY_TYPE, None)
        meta = by_id.get("task")
        title = getattr(meta, "name", None) if meta is not None else None
        label = title if isinstance(title, str) and title.strip() else "task"
        stages = resolve_task_board_stages(crm, key)
        boards.append(
            {
                "board_key": key,
                "label": label,
                "stages": [s.model_dump() for s in stages],
                "uses_custom_preset": key in crm.pipeline_stage_presets,
            }
        )

    for tid in sorted(allowed):
        if tid == "task":
            continue
        meta = by_id.get(tid)
        parent = getattr(meta, "parent_type_id", None) if meta is not None else None
        if parent != TASK_ENTITY_TYPE:
            continue
        key = task_board_key(TASK_ENTITY_TYPE, tid)
        title = getattr(meta, "name", None) if meta is not None else None
        label = title if isinstance(title, str) and title.strip() else tid
        stages = resolve_task_board_stages(crm, key)
        boards.append(
            {
                "board_key": key,
                "label": label,
                "stages": [s.model_dump() for s in stages],
                "uses_custom_preset": key in crm.pipeline_stage_presets,
            }
        )
    return boards


def parse_task_board_presets_from_payload(
    raw: dict[str, Any],
) -> dict[str, TaskBoardPreset]:
    """Разбор сохранённого тела PUT без смягчения: невалидные ключи — исключение."""
    out: dict[str, TaskBoardPreset] = {}
    for raw_key, raw_val in raw.items():
        if not isinstance(raw_key, str):
            raise ValueError("pipeline_stage_presets: ключи должны быть строками")
        key = raw_key.strip()
        if not key:
            raise ValueError("pipeline_stage_presets: пустой ключ")
        if not isinstance(raw_val, dict):
            raise ValueError(f"pipeline_stage_presets[{key!r}]: ожидался объект")
        out[key] = TaskBoardPreset.model_validate(raw_val)
    return out
