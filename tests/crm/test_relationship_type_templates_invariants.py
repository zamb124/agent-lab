"""Инварианты SYSTEM_RELATIONSHIP_TYPE_TEMPLATES.

Проверяется:
- уникальность type_id;
- inverse_type_id указывает на существующий тип;
- prompt у AI-используемых типов длиннее минимального порога и содержит
  блоки «когда / примеры / когда НЕ»;
- системные типы reports_to/manages/attended/owner_of присутствуют.
"""

from typing import Any

import pytest

from apps.crm.system_templates import (
    SYSTEM_RELATIONSHIP_TYPE_TEMPLATES,
    RelationshipTypeTemplate,
)

_MIN_PROMPT_CHARS = 150


def _by_id() -> dict[str, RelationshipTypeTemplate]:
    return {spec["type_id"]: spec for spec in SYSTEM_RELATIONSHIP_TYPE_TEMPLATES}


def test_relationship_type_ids_are_unique() -> None:
    seen: set[str] = set()
    for spec in SYSTEM_RELATIONSHIP_TYPE_TEMPLATES:
        tid = spec["type_id"]
        assert tid not in seen, tid
        seen.add(tid)


@pytest.mark.parametrize("spec", SYSTEM_RELATIONSHIP_TYPE_TEMPLATES, ids=lambda s: s["type_id"])
def test_relationship_type_has_name_and_description(spec: dict[str, Any]) -> None:
    name = spec.get("name")
    description = spec.get("description")
    assert isinstance(name, str) and len(name.strip()) >= 2, spec["type_id"]
    assert isinstance(description, str) and len(description.strip()) >= 20, spec["type_id"]


@pytest.mark.parametrize("spec", SYSTEM_RELATIONSHIP_TYPE_TEMPLATES, ids=lambda s: s["type_id"])
def test_relationship_inverse_resolves(spec: dict[str, Any]) -> None:
    inverse = spec.get("inverse_type_id")
    if inverse is None:
        return
    by_id = _by_id()
    assert inverse in by_id, (spec["type_id"], inverse)
    assert by_id[inverse].get("inverse_type_id") == spec["type_id"], (spec["type_id"], inverse)


@pytest.mark.parametrize(
    "spec",
    [s for s in SYSTEM_RELATIONSHIP_TYPE_TEMPLATES if s.get("prompt") is not None],
    ids=lambda s: s["type_id"],
)
def test_relationship_prompt_is_long_and_structured(spec: dict[str, Any]) -> None:
    prompt = spec["prompt"]
    assert isinstance(prompt, str), spec["type_id"]
    assert len(prompt) >= _MIN_PROMPT_CHARS, (
        spec["type_id"],
        f"prompt too short ({len(prompt)} < {_MIN_PROMPT_CHARS})",
    )
    lower = prompt.lower()
    assert "когда использовать" in lower, spec["type_id"]
    assert "пример" in lower, spec["type_id"]
    assert "когда не" in lower, spec["type_id"]


def test_required_system_relationship_types_present() -> None:
    by_id = _by_id()
    for tid in (
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
        assert tid in by_id, tid


def test_directed_pairs_are_consistent() -> None:
    """`parent_of`↔`child_of`, `blocks`↔`blocked_by`, `reports_to`↔`manages` парны."""
    by_id = _by_id()
    pairs = (
        ("parent_of", "child_of"),
        ("blocks", "blocked_by"),
        ("reports_to", "manages"),
    )
    for a, b in pairs:
        assert by_id[a].get("inverse_type_id") == b, (a, b)
        assert by_id[b].get("inverse_type_id") == a, (a, b)
        assert by_id[a].get("is_directed") is True, a
        assert by_id[b].get("is_directed") is True, b
