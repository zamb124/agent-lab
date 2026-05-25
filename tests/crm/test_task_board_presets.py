"""Резолвер стадий доски задач CRM."""

import pytest

from apps.crm.services.task_board_presets import (
    default_task_board_stages,
    resolve_task_board_stages,
    task_board_key,
)
from core.models.identity_models import BoardStage, NamespaceCRMSettings, TaskBoardPreset


def test_task_board_key() -> None:
    assert task_board_key("task", None) == "task"
    assert task_board_key("task", "") == "task"
    assert task_board_key("task", "bug") == "task:bug"
    with pytest.raises(ValueError):
        task_board_key("deal", None)


def test_resolve_default_when_no_preset() -> None:
    crm = NamespaceCRMSettings()
    stages = resolve_task_board_stages(crm, "task")
    assert [s.id for s in stages] == ["todo", "in_progress", "done"]


def test_resolve_custom_preset() -> None:
    crm = NamespaceCRMSettings(
        pipeline_stage_presets={
            "task": TaskBoardPreset(
                stages=[
                    BoardStage(stage_id="open", label="Открыто"),
                    BoardStage(stage_id="closed", label="Закрыто"),
                ]
            )
        }
    )
    stages = resolve_task_board_stages(crm, "task")
    assert [s.id for s in stages] == ["open", "closed"]


def test_default_task_board_three_stages() -> None:
    d = default_task_board_stages()
    assert len(d) == 3
