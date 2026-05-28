"""Инварианты системных шаблонов entity types: ядро, якоря, типы из seed-пакетов.

Проверяется канон, описанный в `apps/crm/system_templates.py`:
- name + description у каждого типа,
- prompt с минимальной длиной у extractable-типов,
- у каждого поля required/optional есть type + label + description,
- enum-поле содержит непустой values и описание каждого значения.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

import pytest

from apps.crm.system_templates import (
    COMMON_NAMESPACE_ANCHOR_TYPES,
    EntityTypeTemplate,
    NAMESPACE_TEMPLATE_SEEDS,
    NamespaceTemplateTypeSpec,
    SYSTEM_ENTITY_TYPE_TEMPLATES,
)
from tests.crm.e2e._json_helpers import object_dict, object_str

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
        for type_spec in seed["types"]:
            yield (f"seed:{seed['template_id']}:{type_spec['type_id']}", type_spec)


def _is_extractable(spec: EntityTypeTemplate | NamespaceTemplateTypeSpec) -> bool:
    return bool(spec.get("extractable", True))


ALL_ENTITY_TYPE_SPECS = list(_all_entity_type_specs())
EXTRACTABLE_ENTITY_TYPE_SPECS = [
    pair for pair in ALL_ENTITY_TYPE_SPECS if _is_extractable(pair[1])
]
NON_EXTRACTABLE_ENTITY_TYPE_SPECS = [
    pair for pair in ALL_ENTITY_TYPE_SPECS if not _is_extractable(pair[1])
]


def _all_fields(
    spec: EntityTypeTemplate | NamespaceTemplateTypeSpec,
) -> Iterable[tuple[str, str, dict[str, object]]]:
    for section in ("required_fields", "optional_fields"):
        bag = object_dict(spec.get(section) or {}, field=section)
        for field_name, field_spec_value in bag.items():
            field_name_str = object_str(field_name, field=f"{section} field name")
            field_spec = object_dict(
                field_spec_value,
                field=f"{section}.{field_name_str}",
            )
            yield (section, field_name_str, field_spec)


@pytest.mark.parametrize(
    ("ctx", "spec"),
    ALL_ENTITY_TYPE_SPECS,
    ids=[ctx for ctx, _spec in ALL_ENTITY_TYPE_SPECS],
)
def test_entity_type_has_name_and_description(
    ctx: str,
    spec: EntityTypeTemplate | NamespaceTemplateTypeSpec,
) -> None:
    name = spec.get("name")
    assert isinstance(name, str) and len(name.strip()) >= 2, ctx
    description = spec.get("description")
    assert isinstance(description, str), ctx
    assert len(description.strip()) >= _MIN_TYPE_DESCRIPTION_CHARS, (
        ctx,
        f"description too short ({len(description.strip())} < {_MIN_TYPE_DESCRIPTION_CHARS})",
    )


@pytest.mark.parametrize(
    ("ctx", "spec"),
    EXTRACTABLE_ENTITY_TYPE_SPECS,
    ids=[ctx for ctx, _spec in EXTRACTABLE_ENTITY_TYPE_SPECS],
)
def test_extractable_entity_type_has_useful_prompt(
    ctx: str,
    spec: EntityTypeTemplate | NamespaceTemplateTypeSpec,
) -> None:
    prompt = spec.get("prompt")
    assert isinstance(prompt, str) and len(prompt.strip()) >= _MIN_PROMPT_CHARS, (
        ctx,
        f"prompt for extractable type too short ({len(prompt or '')} < {_MIN_PROMPT_CHARS})",
    )


@pytest.mark.parametrize(
    ("ctx", "spec"),
    NON_EXTRACTABLE_ENTITY_TYPE_SPECS,
    ids=[ctx for ctx, _spec in NON_EXTRACTABLE_ENTITY_TYPE_SPECS],
)
def test_non_extractable_entity_type_has_no_required_prompt(
    ctx: str,
    spec: EntityTypeTemplate | NamespaceTemplateTypeSpec,
) -> None:
    prompt = spec.get("prompt")
    assert prompt is None or isinstance(prompt, str), ctx


@pytest.mark.parametrize(
    ("ctx", "spec"),
    ALL_ENTITY_TYPE_SPECS,
    ids=[ctx for ctx, _spec in ALL_ENTITY_TYPE_SPECS],
)
def test_entity_type_fields_have_label_and_description(
    ctx: str,
    spec: EntityTypeTemplate | NamespaceTemplateTypeSpec,
) -> None:
    for section, field_name, field_spec in _all_fields(spec):
        where = f"{ctx}.{section}[{field_name}]"
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
    ("ctx", "spec"),
    ALL_ENTITY_TYPE_SPECS,
    ids=[ctx for ctx, _spec in ALL_ENTITY_TYPE_SPECS],
)
def test_enum_fields_have_values_and_per_value_description(
    ctx: str,
    spec: EntityTypeTemplate | NamespaceTemplateTypeSpec,
) -> None:
    for section, field_name, field_spec in _all_fields(spec):
        if field_spec.get("type") != "enum":
            continue
        where = f"{ctx}.{section}[{field_name}]"
        values_raw = field_spec.get("values")
        if not isinstance(values_raw, list):
            raise AssertionError(f"{where}: values must be a list")
        values = [
            object_str(enum_item, field="enum value")
            for enum_item in cast(list[object], values_raw)
        ]
        assert len(values) > 0, where
        assert len(set(values)) == len(values), (where, "duplicate enum values")
        description = object_str(field_spec.get("description") or "", field="description")
        for enum_value in values:
            assert enum_value in description, (
                where,
                f"enum value `{enum_value}` not described in field description",
            )


def test_seeded_packages_include_required_anchors_and_core() -> None:
    """Каждый пакет содержит note, task и общие якоря topic/organization/project."""
    expected = {"note", "task", "topic", "organization", "project"}
    for seed in NAMESPACE_TEMPLATE_SEEDS:
        type_ids = {type_spec["type_id"] for type_spec in seed["types"]}
        missing = expected - type_ids
        assert not missing, (seed["template_id"], sorted(missing))


def test_note_family_is_not_context_anchor() -> None:
    """Заметки/встречи/звонки не являются якорями контекста (in_context их не принимает)."""
    by_id = {spec["type_id"]: spec for spec in SYSTEM_ENTITY_TYPE_TEMPLATES}
    for type_id in ("note", "meeting", "call"):
        type_spec = by_id[type_id]
        assert type_spec.get("is_context_anchor") is False, type_id


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
    for type_spec in COMMON_NAMESPACE_ANCHOR_TYPES:
        assert type_spec.get("is_context_anchor") is True, type_spec["type_id"]
