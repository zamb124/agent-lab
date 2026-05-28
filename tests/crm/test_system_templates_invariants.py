"""Инварианты системных шаблонов entity types: ядро, якоря, типы из seed-пакетов.

Проверяется канон, описанный в `apps/crm/system_templates.py`:
- name + description у каждого типа,
- prompt с минимальной длиной у extractable-типов,
- у каждого поля required/optional есть type + label + description,
- enum-поле содержит непустой values и описание каждого значения.
"""

from typing import Any, Iterable

import pytest

from apps.crm.system_templates import (
    COMMON_NAMESPACE_ANCHOR_TYPES,
    EntityTypeTemplate,
    NAMESPACE_TEMPLATE_SEEDS,
    NamespaceTemplateTypeSpec,
    SYSTEM_ENTITY_TYPE_TEMPLATES,
)

_MIN_TYPE_DESCRIPTION_CHARS = 30
_MIN_PROMPT_CHARS = 120
_MIN_FIELD_LABEL_CHARS = 2
_MIN_FIELD_DESCRIPTION_CHARS = 10

_FIELD_TYPES_ALLOWED = {
    "string",
    "text",
    "number",
    "integer",
    "boolean",
    "date",
    "datetime",
    "enum",
    "array",
    "object",
}


def _all_entity_type_specs() -> Iterable[tuple[str, EntityTypeTemplate | NamespaceTemplateTypeSpec]]:
    """Возвращает (метка_контекста, spec) по всем системным типам платформы."""
    for spec in SYSTEM_ENTITY_TYPE_TEMPLATES:
        yield (f"system:{spec['type_id']}", spec)
    for spec in COMMON_NAMESPACE_ANCHOR_TYPES:
        yield (f"common_anchor:{spec['type_id']}", spec)
    for seed in NAMESPACE_TEMPLATE_SEEDS:
        for spec in seed["types"]:
            yield (f"seed:{seed['template_id']}:{spec['type_id']}", spec)


def _is_extractable(spec: EntityTypeTemplate | NamespaceTemplateTypeSpec) -> bool:
    return bool(spec.get("extractable", True))


@pytest.mark.parametrize(
    "ctx,spec",
    list(_all_entity_type_specs()),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_entity_type_has_name_and_description(ctx: str, spec: EntityTypeTemplate | NamespaceTemplateTypeSpec) -> None:
    name = spec.get("name")
    assert isinstance(name, str) and len(name.strip()) >= 2, ctx
    description = spec.get("description")
    assert isinstance(description, str), ctx
    assert len(description.strip()) >= _MIN_TYPE_DESCRIPTION_CHARS, (
        ctx,
        f"description too short ({len(description.strip())} < {_MIN_TYPE_DESCRIPTION_CHARS})",
    )


@pytest.mark.parametrize(
    "ctx,spec",
    [pair for pair in _all_entity_type_specs() if _is_extractable(pair[1])],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_extractable_entity_type_has_useful_prompt(
    ctx: str, spec: EntityTypeTemplate | NamespaceTemplateTypeSpec
) -> None:
    prompt = spec.get("prompt")
    assert isinstance(prompt, str) and len(prompt.strip()) >= _MIN_PROMPT_CHARS, (
        ctx,
        f"prompt for extractable type too short ({len(prompt or '')} < {_MIN_PROMPT_CHARS})",
    )


@pytest.mark.parametrize(
    "ctx,spec",
    [pair for pair in _all_entity_type_specs() if not _is_extractable(pair[1])],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_non_extractable_entity_type_has_no_required_prompt(
    ctx: str, spec: EntityTypeTemplate | NamespaceTemplateTypeSpec
) -> None:
    prompt = spec.get("prompt")
    assert prompt is None or isinstance(prompt, str), ctx


def _all_fields(
    spec: EntityTypeTemplate | NamespaceTemplateTypeSpec,
) -> Iterable[tuple[str, str, dict[str, Any]]]:
    for section in ("required_fields", "optional_fields"):
        bag = spec.get(section) or {}
        if not isinstance(bag, dict):
            raise AssertionError(f"{section} must be a dict in {spec.get('type_id')}")
        for field_name, field_spec in bag.items():
            yield (section, field_name, field_spec)


@pytest.mark.parametrize(
    "ctx,spec",
    list(_all_entity_type_specs()),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_entity_type_fields_have_label_and_description(
    ctx: str, spec: EntityTypeTemplate | NamespaceTemplateTypeSpec
) -> None:
    for section, field_name, field_spec in _all_fields(spec):
        where = f"{ctx}.{section}[{field_name}]"
        assert isinstance(field_spec, dict), where
        ftype = field_spec.get("type")
        assert ftype in _FIELD_TYPES_ALLOWED, (where, ftype)
        label = field_spec.get("label")
        assert isinstance(label, str) and len(label.strip()) >= _MIN_FIELD_LABEL_CHARS, where
        description = field_spec.get("description")
        assert isinstance(description, str), where
        assert len(description.strip()) >= _MIN_FIELD_DESCRIPTION_CHARS, (
            where,
            f"description too short ({len(description.strip())} < {_MIN_FIELD_DESCRIPTION_CHARS})",
        )


@pytest.mark.parametrize(
    "ctx,spec",
    list(_all_entity_type_specs()),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_enum_fields_have_values_and_per_value_description(
    ctx: str, spec: EntityTypeTemplate | NamespaceTemplateTypeSpec
) -> None:
    for section, field_name, field_spec in _all_fields(spec):
        if field_spec.get("type") != "enum":
            continue
        where = f"{ctx}.{section}[{field_name}]"
        values = field_spec.get("values")
        assert isinstance(values, list) and len(values) > 0, where
        for v in values:
            assert isinstance(v, str) and len(v) > 0, (where, v)
            assert len(set(values)) == len(values), (where, "duplicate enum values")
        description = field_spec.get("description") or ""
        for v in values:
            assert v in description, (where, f"enum value `{v}` not described in field description")


def test_seeded_packages_include_required_anchors_and_core() -> None:
    """Каждый пакет содержит note, task и общие якоря topic/organization/project."""
    expected = {"note", "task", "topic", "organization", "project"}
    for seed in NAMESPACE_TEMPLATE_SEEDS:
        ids = {t["type_id"] for t in seed["types"] if isinstance(t, dict)}
        missing = expected - ids
        assert not missing, (seed["template_id"], sorted(missing))


def test_note_family_is_not_context_anchor() -> None:
    """Заметки/встречи/звонки не являются якорями контекста (in_context их не принимает)."""
    by_id = {spec["type_id"]: spec for spec in SYSTEM_ENTITY_TYPE_TEMPLATES}
    for tid in ("note", "meeting", "call"):
        spec = by_id[tid]
        assert spec.get("is_context_anchor") is False, tid


def test_task_root_is_not_context_anchor() -> None:
    """Корневой task — это инструмент, а не якорь контекста."""
    by_id = {spec["type_id"]: spec for spec in SYSTEM_ENTITY_TYPE_TEMPLATES}
    assert by_id["task"].get("is_context_anchor") is False


def test_member_and_contact_are_voice_targets() -> None:
    """Voice заметки можно ставить только на person-сущностей."""
    by_id = {spec["type_id"]: spec for spec in SYSTEM_ENTITY_TYPE_TEMPLATES}
    assert by_id["member"].get("is_voice_target") is True
    assert by_id["contact"].get("is_voice_target") is True


def test_common_anchor_types_are_context_anchors() -> None:
    for spec in COMMON_NAMESPACE_ANCHOR_TYPES:
        assert spec.get("is_context_anchor") is True, spec["type_id"]
