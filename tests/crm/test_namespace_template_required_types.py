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
