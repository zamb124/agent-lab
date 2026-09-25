from __future__ import annotations

import pytest

from apps.crm.models.entity_type import EntityType
from apps.crm.models.relationship_type import RelationshipType
from apps.crm.services.entity_service import (
    _ANALYZE_BUDGET_USER_MESSAGE,  # pyright: ignore[reportPrivateUsage]
    EntityService,
)


def _entity_service_stub() -> EntityService:
    return EntityService.__new__(EntityService)


def test_analyze_preflight_rejects_oversized_text() -> None:
    service = _entity_service_stub()
    entity_types = [
        EntityType(
            company_id="budget",
            namespace="default",
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
            company_id="budget",
            name="Mentions",
            prompt="Mention link",
        )
    ]
    oversized_text = "слово " * 200_000

    with pytest.raises(ValueError, match=_ANALYZE_BUDGET_USER_MESSAGE):
        service._assert_analyze_text_fits_llm_budget(  # pyright: ignore[reportPrivateUsage]
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
            company_id="budget",
            namespace="default",
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
            company_id="budget",
            name="Mentions",
            prompt="Mention link",
        )
    ]

    service._assert_analyze_text_fits_llm_budget(  # pyright: ignore[reportPrivateUsage]
        text="Короткая заметка о встрече с клиентом.",
        entity_types=entity_types,
        relationship_types=relationship_types,
        extract_entity_types=None,
        extract_relationship_types=None,
        known_entities=None,
    )
