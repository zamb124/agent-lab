"""Инварианты NAMESPACE_TEMPLATE_SEEDS.

Проверяются метаданные пакетов (template_id уникален, name/description
есть) и `crm_settings.pipeline_stage_presets`: каждый ключ — валидный
`task_board_key`, каждая доска — валидный `TaskBoardPreset` с непустыми
уникальными стадиями.
"""

from typing import Any

import pytest

from apps.crm.constants_graph import TASK_ROOT_ENTITY_TYPE_ID
from apps.crm.services.task_board_presets import (
    TASK_ENTITY_TYPE,
    parse_task_board_presets_from_payload,
)
from apps.crm.system_templates import NAMESPACE_TEMPLATE_SEEDS

_TEMPLATE_ID_PATTERN = "^[a-z][a-z0-9_]*$"
_BOARD_STAGE_ID_PATTERN = "^[a-z][a-z0-9_]*$"


def test_template_ids_are_unique() -> None:
    seen: set[str] = set()
    for seed in NAMESPACE_TEMPLATE_SEEDS:
        tid = seed["template_id"]
        assert tid not in seen, tid
        seen.add(tid)


@pytest.mark.parametrize(
    "seed", NAMESPACE_TEMPLATE_SEEDS, ids=lambda s: s["template_id"]
)
def test_seed_has_required_metadata(seed: dict[str, Any]) -> None:
    import re

    tid = seed.get("template_id")
    assert isinstance(tid, str), seed
    assert re.match(_TEMPLATE_ID_PATTERN, tid), tid
    name = seed.get("name")
    description = seed.get("description")
    icon = seed.get("icon")
    assert isinstance(name, str) and len(name.strip()) >= 2, tid
    assert isinstance(description, str) and len(description.strip()) >= 30, tid
    assert isinstance(icon, str) and len(icon.strip()) >= 2, tid


@pytest.mark.parametrize(
    "seed", NAMESPACE_TEMPLATE_SEEDS, ids=lambda s: s["template_id"]
)
def test_seed_crm_settings_has_pipeline_stage_presets(seed: dict[str, Any]) -> None:
    crm_settings = seed.get("crm_settings")
    assert isinstance(crm_settings, dict), seed["template_id"]
    presets = crm_settings.get("pipeline_stage_presets")
    assert isinstance(presets, dict) and len(presets) > 0, seed["template_id"]


@pytest.mark.parametrize(
    "seed", NAMESPACE_TEMPLATE_SEEDS, ids=lambda s: s["template_id"]
)
def test_seed_pipeline_stage_presets_parse(seed: dict[str, Any]) -> None:
    presets_raw = seed["crm_settings"]["pipeline_stage_presets"]
    parse_task_board_presets_from_payload(presets_raw)


@pytest.mark.parametrize(
    "seed", NAMESPACE_TEMPLATE_SEEDS, ids=lambda s: s["template_id"]
)
def test_seed_pipeline_stage_preset_keys_match_existing_subtypes(
    seed: dict[str, Any],
) -> None:
    """Ключи `task:<subtype>` должны соответствовать типам, чей parent — task."""
    type_ids_with_task_parent: set[str] = set()
    for type_spec in seed["types"]:
        parent = type_spec.get("parent_type_id")
        if parent == TASK_ROOT_ENTITY_TYPE_ID:
            type_ids_with_task_parent.add(type_spec["type_id"])

    for raw_key in seed["crm_settings"]["pipeline_stage_presets"].keys():
        key = raw_key.strip()
        if key == TASK_ENTITY_TYPE:
            continue
        prefix = f"{TASK_ENTITY_TYPE}:"
        assert key.startswith(prefix), (seed["template_id"], key)
        subtype = key[len(prefix):]
        assert subtype in type_ids_with_task_parent, (
            seed["template_id"],
            key,
            f"subtype `{subtype}` is not a task subtype in this template",
        )


@pytest.mark.parametrize(
    "seed", NAMESPACE_TEMPLATE_SEEDS, ids=lambda s: s["template_id"]
)
def test_seed_pipeline_stage_preset_stage_ids_are_snake_case_unique(
    seed: dict[str, Any],
) -> None:
    import re

    presets = parse_task_board_presets_from_payload(
        seed["crm_settings"]["pipeline_stage_presets"]
    )
    for board_key, preset in presets.items():
        stage_ids = [stage.id for stage in preset.stages]
        assert len(stage_ids) >= 2, (seed["template_id"], board_key)
        assert len(set(stage_ids)) == len(stage_ids), (
            seed["template_id"],
            board_key,
            "duplicate stage ids",
        )
        for stage_id in stage_ids:
            assert re.match(_BOARD_STAGE_ID_PATTERN, stage_id), (
                seed["template_id"],
                board_key,
                stage_id,
            )


@pytest.mark.parametrize(
    "seed", NAMESPACE_TEMPLATE_SEEDS, ids=lambda s: s["template_id"]
)
def test_seed_default_note_voice_is_self(seed: dict[str, Any]) -> None:
    crm_settings = seed["crm_settings"]
    assert crm_settings.get("default_note_voice") == "self", seed["template_id"]
    assert crm_settings.get("show_note_voice_ui") is True, seed["template_id"]


def test_expected_seeds_present() -> None:
    """Полный набор системных seed-пакетов, который платформа гарантирует."""
    expected = {
        "sales",
        "agile_project",
        "development",
        "hr",
        "marketing",
        "support",
        "product_management",
        "recruiting",
        "real_estate",
        "legal",
        "finance",
        "education",
    }
    actual = {seed["template_id"] for seed in NAMESPACE_TEMPLATE_SEEDS}
    missing = expected - actual
    assert not missing, sorted(missing)


@pytest.mark.parametrize(
    "seed", NAMESPACE_TEMPLATE_SEEDS, ids=lambda s: s["template_id"]
)
def test_seed_type_ids_unique_within_seed(seed: dict[str, Any]) -> None:
    seen: set[str] = set()
    for type_spec in seed["types"]:
        tid = type_spec["type_id"]
        assert tid not in seen, (seed["template_id"], tid)
        seen.add(tid)
