"""Инварианты NAMESPACE_TEMPLATE_SEEDS.

Проверяются метаданные пакетов (template_id уникален, name/description/icon есть),
настройки голоса заметок и уникальность type_id внутри пакета. Канбан-доски задач
больше не живут в CRM (work-семантика — в ядре WorkItem), поэтому пресетов стадий
в seed-пакетах нет.
"""

from __future__ import annotations

import re

import pytest

from apps.crm.system_templates import NAMESPACE_TEMPLATE_SEEDS, NamespaceTemplateSeed
from tests.crm.e2e._json_helpers import object_dict

_TEMPLATE_ID_PATTERN = "^[a-z][a-z0-9_]*$"


def _seed_template_id(seed: NamespaceTemplateSeed) -> str:
    return seed["template_id"]


def _crm_settings(seed: NamespaceTemplateSeed) -> dict[str, object]:
    return object_dict(seed.get("crm_settings"), field="crm_settings")


def test_template_ids_are_unique() -> None:
    seen: set[str] = set()
    for seed in NAMESPACE_TEMPLATE_SEEDS:
        template_id = seed["template_id"]
        assert template_id not in seen, template_id
        seen.add(template_id)


@pytest.mark.parametrize("seed", NAMESPACE_TEMPLATE_SEEDS, ids=_seed_template_id)
def test_seed_has_required_metadata(seed: NamespaceTemplateSeed) -> None:
    template_id = seed["template_id"]
    assert re.match(_TEMPLATE_ID_PATTERN, template_id), template_id
    name = seed["name"]
    description = seed["description"]
    icon = seed["icon"]
    assert len(name.strip()) >= 2, template_id
    assert len(description.strip()) >= 30, template_id
    assert len(icon.strip()) >= 2, template_id


@pytest.mark.parametrize("seed", NAMESPACE_TEMPLATE_SEEDS, ids=_seed_template_id)
def test_seed_crm_settings_has_no_pipeline_stage_presets(seed: NamespaceTemplateSeed) -> None:
    """Доски задач переехали в worktracker — пресетов стадий в CRM seed быть не должно."""
    assert "pipeline_stage_presets" not in _crm_settings(seed), seed["template_id"]


@pytest.mark.parametrize("seed", NAMESPACE_TEMPLATE_SEEDS, ids=_seed_template_id)
def test_seed_default_note_voice_is_self(seed: NamespaceTemplateSeed) -> None:
    crm_settings = _crm_settings(seed)
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


@pytest.mark.parametrize("seed", NAMESPACE_TEMPLATE_SEEDS, ids=_seed_template_id)
def test_seed_type_ids_unique_within_seed(seed: NamespaceTemplateSeed) -> None:
    seen: set[str] = set()
    for type_spec in seed["types"]:
        type_id = type_spec["type_id"]
        assert type_id not in seen, (seed["template_id"], type_id)
        seen.add(type_id)
