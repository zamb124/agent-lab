"""Инварианты шаблонов пространств: note и task."""

from apps.crm.system_templates import (
    NAMESPACE_TEMPLATE_SEEDS,
    REQUIRED_NAMESPACE_TEMPLATE_TYPE_IDS,
    NamespaceTemplateSeed,
)


def test_every_namespace_template_seed_has_note_and_task() -> None:
    for seed in NAMESPACE_TEMPLATE_SEEDS:
        template_id = seed["template_id"]
        type_ids = {type_spec["type_id"] for type_spec in seed["types"]}
        missing = REQUIRED_NAMESPACE_TEMPLATE_TYPE_IDS - type_ids
        assert not missing, f"template {template_id} missing types: {sorted(missing)}"


def test_namespace_template_seeds_exclude_retired_amocrm() -> None:
    template_ids = {seed["template_id"] for seed in NAMESPACE_TEMPLATE_SEEDS}
    assert "amocrm" not in template_ids


def test_sales_seed_includes_contact_and_task() -> None:
    sales = _seed_by_id("sales")
    type_ids = {type_spec["type_id"] for type_spec in sales["types"]}
    assert "contact" in type_ids
    assert "task" in type_ids


def _seed_by_id(template_id: str) -> NamespaceTemplateSeed:
    for seed in NAMESPACE_TEMPLATE_SEEDS:
        if seed["template_id"] == template_id:
            return seed
    raise AssertionError(f"seed {template_id!r} not registered")
