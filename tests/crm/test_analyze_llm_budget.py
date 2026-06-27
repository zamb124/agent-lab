from __future__ import annotations

import pytest

from apps.crm.db.models import EntityType, RelationshipType
from apps.crm.services.entity_service import _ANALYZE_BUDGET_USER_MESSAGE, EntityService


def _entity_service_stub() -> EntityService:
    return EntityService.__new__(EntityService)


def test_analyze_preflight_rejects_oversized_text() -> None:
    service = _entity_service_stub()
    entity_types = [
        EntityType(
            type_id="note",
            name="Note",
            prompt="Extract note",
            extractable=True,
            required_fields={},
            optional_fields={},
        )
    ]
    relationship_types = [
        RelationshipType(
            type_id="mentions",
            name="Mentions",
            prompt="Mention link",
        )
    ]
    oversized_text = "слово " * 200_000

    with pytest.raises(ValueError, match=_ANALYZE_BUDGET_USER_MESSAGE):
        service._assert_analyze_text_fits_llm_budget(
            text=oversized_text,
            entity_types=entity_types,
            relationship_types=relationship_types,
            extract_entity_types=None,
            extract_relationship_types=None,
            known_entities=None,
        )


def test_analyze_preflight_accepts_short_text() -> None:
    service = _entity_service_stub()
    entity_types = [
        EntityType(
            type_id="note",
            name="Note",
            prompt="Extract note",
            extractable=True,
            required_fields={},
            optional_fields={},
        )
    ]
    relationship_types = [
        RelationshipType(
            type_id="mentions",
            name="Mentions",
            prompt="Mention link",
        )
    ]

    service._assert_analyze_text_fits_llm_budget(
        text="Короткая заметка о встрече с клиентом.",
        entity_types=entity_types,
        relationship_types=relationship_types,
        extract_entity_types=None,
        extract_relationship_types=None,
        known_entities=None,
    )
