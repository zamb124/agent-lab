"""Форматирование Markdown заметки: TextTransformService через MockLLM, OCC по description."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio

from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID
from apps.crm.di import CrmDi
from apps.crm.models.crm_entity import CRMEntity
from apps.crm.tasks.note_markdown_tasks import format_note_description_markdown_task
from core.utils.tokens import get_token_service
from tests.fixtures.service_processes import ServiceProcesses

_COMPANY_ID = "system"


@pytest_asyncio.fixture
async def di(service_processes: ServiceProcesses) -> CrmDi:
    return await service_processes.di(CrmDi)


async def _seed_note(unique_id: str, description: str) -> CRMEntity:
    return await CRMEntity.create(
        CRMEntity(
            entity_id=f"note_md_{unique_id}",
            company_id=_COMPANY_ID,
            namespace=f"md_ns_{unique_id}",
            entity_type=NOTE_ROOT_ENTITY_TYPE_ID,
            name=f"Note {unique_id}",
            description=description,
            user_id="test_user",
            note_date=datetime(2026, 1, 9, tzinfo=UTC),
            attributes={},
        )
    )


@pytest.mark.asyncio
async def test_note_markdown_format_replaces_description_with_one_transform_call(
    di: CrmDi,
    mock_llm_redis,
    mock_llm_capture,
    unique_id: str,
) -> None:
    full_text = "alpha\n\n" * 800
    note = await _seed_note(unique_id, full_text)
    _ = await di.namespace_service.get_or_create(
        note.namespace, description="markdown format test"
    )
    await mock_llm_redis([{"type": "text", "content": "# ok\n"}])

    result = await format_note_description_markdown_task(
        note.entity_id,
        _COMPANY_ID,
        note.namespace,
        get_token_service().create_token("test_user", company_id=_COMPANY_ID),
        "test_user",
        "ru",
        di=di,
    )

    assert result == {
        "status": "completed",
        "note_id": note.entity_id,
        "chunks_total": 1,
        "chunks_processed": 1,
    }
    assert len(await mock_llm_capture()) == 1
    stored = await CRMEntity.get(note.entity_id)
    assert stored is not None
    assert stored.description == "# ok"


@pytest.mark.asyncio
async def test_description_update_is_skipped_when_description_changed(unique_id: str) -> None:
    note = await _seed_note(unique_id, "hello")

    merged = await CRMEntity.update_description_if_current(
        note.entity_id,
        expected_description="hello, edited by the user meanwhile",
        description="# ok",
    )

    assert merged is None
    stored = await CRMEntity.get(note.entity_id)
    assert stored is not None
    assert stored.description == "hello"
