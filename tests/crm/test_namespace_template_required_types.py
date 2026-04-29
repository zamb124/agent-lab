"""Инварианты шаблонов пространств: note и task."""

from apps.crm.system_templates import (
    NAMESPACE_TEMPLATE_SEEDS,
    REQUIRED_NAMESPACE_TEMPLATE_TYPE_IDS,
)


def test_every_namespace_template_seed_has_note_and_task() -> None:
    for seed in NAMESPACE_TEMPLATE_SEEDS:
        tid = seed.get("template_id")
        types_list = seed.get("types")
        assert isinstance(types_list, list), tid
        ids = {t["type_id"] for t in types_list if isinstance(t, dict) and "type_id" in t}
        missing = REQUIRED_NAMESPACE_TEMPLATE_TYPE_IDS - ids
        assert not missing, f"template {tid} missing types: {sorted(missing)}"


def test_namespace_template_seeds_exclude_retired_amocrm() -> None:
    ids = {s["template_id"] for s in NAMESPACE_TEMPLATE_SEEDS if isinstance(s, dict)}
    assert "amocrm" not in ids


def test_sales_seed_includes_contact_and_task() -> None:
    sales = next(s for s in NAMESPACE_TEMPLATE_SEEDS if s["template_id"] == "sales")
    type_ids = {t["type_id"] for t in sales["types"] if isinstance(t, dict)}
    assert "contact" in type_ids
    assert "task" in type_ids
