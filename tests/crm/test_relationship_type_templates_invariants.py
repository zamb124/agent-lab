"""Инварианты SYSTEM_RELATIONSHIP_TYPE_TEMPLATES.

Проверяется:
- уникальность type_id;
- inverse_type_id указывает на существующий тип;
- prompt у AI-используемых типов длиннее минимального порога и содержит
  блоки «когда / примеры / когда НЕ»;
- системные типы reports_to/manages/attended/owner_of присутствуют.
"""

from __future__ import annotations

import pytest

from apps.crm.system_templates import (
    SYSTEM_RELATIONSHIP_TYPE_TEMPLATES,
    RelationshipTypeTemplate,
)

_MIN_PROMPT_CHARS = 150

_RELATIONSHIP_TYPES_WITH_PROMPT: list[RelationshipTypeTemplate] = [
    spec
    for spec in SYSTEM_RELATIONSHIP_TYPE_TEMPLATES
    if spec.get("prompt") is not None
]


def _relationship_type_id(spec: RelationshipTypeTemplate) -> str:
    return spec["type_id"]


def _by_id() -> dict[str, RelationshipTypeTemplate]:
    return {spec["type_id"]: spec for spec in SYSTEM_RELATIONSHIP_TYPE_TEMPLATES}


def test_relationship_type_ids_are_unique() -> None:
    seen: set[str] = set()
    for spec in SYSTEM_RELATIONSHIP_TYPE_TEMPLATES:
        type_id = spec["type_id"]
        assert type_id not in seen, type_id
        seen.add(type_id)


@pytest.mark.parametrize(
    "spec",
    SYSTEM_RELATIONSHIP_TYPE_TEMPLATES,
    ids=_relationship_type_id,
)
def test_relationship_type_has_name_and_description(spec: RelationshipTypeTemplate) -> None:
    type_id = spec["type_id"]
    name = spec["name"]
    description = spec["description"]
    assert len(name.strip()) >= 2, type_id
    assert len(description.strip()) >= 20, type_id


@pytest.mark.parametrize(
    "spec",
    SYSTEM_RELATIONSHIP_TYPE_TEMPLATES,
    ids=_relationship_type_id,
)
def test_relationship_inverse_resolves(spec: RelationshipTypeTemplate) -> None:
    inverse = spec.get("inverse_type_id")
    if inverse is None:
        return
    by_id = _by_id()
    assert inverse in by_id, (spec["type_id"], inverse)
    assert by_id[inverse].get("inverse_type_id") == spec["type_id"], (spec["type_id"], inverse)


@pytest.mark.parametrize(
    "spec",
    _RELATIONSHIP_TYPES_WITH_PROMPT,
    ids=_relationship_type_id,
)
def test_relationship_prompt_is_long_and_structured(spec: RelationshipTypeTemplate) -> None:
    prompt = spec.get("prompt")
    type_id = spec["type_id"]
    assert prompt is not None
    assert len(prompt) >= _MIN_PROMPT_CHARS, (
        type_id,
        f"prompt too short ({len(prompt)} < {_MIN_PROMPT_CHARS})",
    )
    lower = prompt.lower()
    assert "когда использовать" in lower, type_id
    assert "пример" in lower, type_id
    assert "когда не" in lower, type_id


def test_required_system_relationship_types_present() -> None:
    by_id = _by_id()
    for type_id in (
        "mentions",
        "linked",
        "related_to",
        "parent_of",
        "child_of",
        "assigned_to",
        "belongs_to",
        "follows_up",
        "blocks",
        "blocked_by",
        "duplicates",
        "reports_to",
        "manages",
        "attended",
        "owner_of",
        "note_voice",
        "in_context",
    ):
        assert type_id in by_id, type_id


def test_directed_pairs_are_consistent() -> None:
    """`parent_of`↔`child_of`, `blocks`↔`blocked_by`, `reports_to`↔`manages` парны."""
    by_id = _by_id()
    pairs = (
        ("parent_of", "child_of"),
        ("blocks", "blocked_by"),
        ("reports_to", "manages"),
    )
    for first_type_id, second_type_id in pairs:
        assert by_id[first_type_id].get("inverse_type_id") == second_type_id, (
            first_type_id,
            second_type_id,
        )
        assert by_id[second_type_id].get("inverse_type_id") == first_type_id, (
            first_type_id,
            second_type_id,
        )
        assert by_id[first_type_id].get("is_directed") is True, first_type_id
        assert by_id[second_type_id].get("is_directed") is True, second_type_id
