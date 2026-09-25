"""Физическое удаление шаблона пространства и его типов."""

from __future__ import annotations

import pytest

from apps.crm.models.namespace_template import NamespaceTemplate, NamespaceTemplateType

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("crm_di")]


async def test_upsert_by_template_key_and_type_id_updates_same_row(unique_id: str) -> None:
    template_key = f"upsert-{unique_id}"
    other_key = f"upsert-other-{unique_id}"
    created = await NamespaceTemplateType.upsert_by_template_key_and_type_id(
        template_key=template_key,
        type_id="note",
        parent_type_id=None,
        name="Note",
        description=None,
        prompt=None,
        required_fields={},
        optional_fields={},
        icon=None,
        color=None,
        is_event=False,
        check_duplicates=True,
        weight_coefficient=1.0,
        namespace_ids=[],
    )
    other = await NamespaceTemplateType.upsert_by_template_key_and_type_id(
        template_key=other_key,
        type_id="note",
        parent_type_id=None,
        name="Other",
        description=None,
        prompt=None,
        required_fields={},
        optional_fields={},
        icon=None,
        color=None,
        is_event=False,
        check_duplicates=True,
        weight_coefficient=1.0,
        namespace_ids=[],
    )
    updated = await NamespaceTemplateType.upsert_by_template_key_and_type_id(
        template_key=template_key,
        type_id="note",
        parent_type_id="parent",
        name="Note renamed",
        description="body",
        prompt="ask",
        required_fields={"title": "string"},
        optional_fields={},
        icon="note",
        color="#fff",
        is_event=True,
        check_duplicates=False,
        weight_coefficient=2.0,
        namespace_ids=[f"ns-{unique_id}"],
        is_context_anchor=True,
        is_voice_target=True,
    )
    assert updated.entry_id == created.entry_id
    assert updated.created_at == created.created_at
    assert updated.name == "Note renamed"
    assert updated.parent_type_id == "parent"
    kept = await NamespaceTemplateType.list_for_template(other_key)
    assert [item.entry_id for item in kept] == [other.entry_id]
    assert kept[0].name == "Other"


async def test_list_for_template_orders_by_type_id(unique_id: str) -> None:
    template_key = f"types-{unique_id}"
    other_key = f"types-other-{unique_id}"
    for type_id, owner_key in (("zeta", template_key), ("alpha", template_key), ("other", other_key)):
        row = NamespaceTemplateType(
            entry_id=f"{unique_id}-{type_id}",
            template_key=owner_key,
            type_id=type_id,
            name=type_id,
        )
        _ = await NamespaceTemplateType.objects.create(instance=row)

    listed = await NamespaceTemplateType.list_for_template(template_key)
    assert [item.type_id for item in listed] == ["alpha", "zeta"]
    assert await NamespaceTemplateType.list_for_template(f"missing-{unique_id}") == []


async def test_delete_template_and_types_by_named_keys(unique_id: str) -> None:
    company_id = f"tpl-{unique_id}"
    template_key = f"key-{unique_id}"
    other_key = f"other-{unique_id}"
    template = NamespaceTemplate(
        template_key=template_key,
        company_id=company_id,
        template_id=f"id-{unique_id}",
        name="Template",
    )
    _ = await NamespaceTemplate.create(template)
    other = NamespaceTemplate(
        template_key=other_key,
        company_id=company_id,
        template_id=f"id-other-{unique_id}",
        name="Other",
    )
    _ = await NamespaceTemplate.create(other)
    for type_id, entry_suffix in (("note", "note"), ("task", "task"), ("kept", "kept")):
        owner_key = other_key if type_id == "kept" else template_key
        row = NamespaceTemplateType(
            entry_id=f"{unique_id}-{entry_suffix}",
            template_key=owner_key,
            type_id=type_id,
            name=type_id,
        )
        _ = await NamespaceTemplateType.objects.create(instance=row)

    removed = await NamespaceTemplateType.delete_by_template_key_and_type_id(template_key, "note")
    assert removed == 1
    assert await NamespaceTemplateType.delete_by_template_key_and_type_id(template_key, "note") == 0
    assert await NamespaceTemplateType.delete_by_template_key_and_type_id(template_key, "missing") == 0

    deleted_types = await NamespaceTemplateType.delete_by_template_key(template_key)
    assert deleted_types == 1
    assert await NamespaceTemplateType.delete_by_template_key(template_key) == 0
    kept = await NamespaceTemplateType.list_for_template(other_key)
    assert [item.type_id for item in kept] == ["kept"]

    assert await NamespaceTemplate.delete_by_id(template_key) is True
    assert await NamespaceTemplate.delete_by_id(template_key) is False
    with pytest.raises(ValueError, match="NamespaceTemplate template_key is required"):
        _ = await NamespaceTemplate.delete_by_id("")
    assert await NamespaceTemplate.by_template_id(company_id, f"id-other-{unique_id}") is not None
