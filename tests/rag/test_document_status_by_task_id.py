"""Чтение DocumentProcessingStatus по уникальному task_id."""

from __future__ import annotations

import pytest

from core.db.models.rag import DocumentProcessingStatus


@pytest.mark.asyncio
async def test_by_task_id_returns_row_or_none(unique_id: str) -> None:
    document_id = f"doc_{unique_id}"
    task_id = f"task_{unique_id}"
    stored = await DocumentProcessingStatus.upsert_pending(
        document_id,
        task_id,
        f"ns_{unique_id}",
        "status.txt",
    )

    found = await DocumentProcessingStatus.by_task_id(task_id)
    assert found is not None
    assert found.document_id == stored.document_id
    assert await DocumentProcessingStatus.by_task_id(f"missing_{unique_id}") is None
    with pytest.raises(ValueError, match="task_id is required"):
        _ = await DocumentProcessingStatus.by_task_id("")


@pytest.mark.asyncio
async def test_get_many_returns_found_document_ids(unique_id: str) -> None:
    first_id = f"doc_a_{unique_id}"
    second_id = f"doc_b_{unique_id}"
    _ = await DocumentProcessingStatus.upsert_pending(
        first_id,
        f"task_a_{unique_id}",
        f"ns_{unique_id}",
        "a.txt",
    )
    _ = await DocumentProcessingStatus.upsert_pending(
        second_id,
        f"task_b_{unique_id}",
        f"ns_{unique_id}",
        "b.txt",
    )

    found = await DocumentProcessingStatus.get_many([first_id, second_id, first_id, f"missing_{unique_id}"])
    assert set(found) == {first_id, second_id}
    assert found[first_id].document_id == first_id
    assert await DocumentProcessingStatus.get_many([]) == {}
    with pytest.raises(ValueError, match="DocumentProcessingStatus document_id is required"):
        _ = await DocumentProcessingStatus.get_many([first_id, ""])


@pytest.mark.asyncio
async def test_by_namespace_and_document_ids_returns_found_rows(unique_id: str) -> None:
    namespace_id = f"ns_{unique_id}"
    other_namespace_id = f"other_{unique_id}"
    first_id = f"doc_a_{unique_id}"
    second_id = f"doc_b_{unique_id}"
    foreign_id = f"doc_c_{unique_id}"
    _ = await DocumentProcessingStatus.upsert_pending(first_id, f"task_a_{unique_id}", namespace_id, "a.txt")
    _ = await DocumentProcessingStatus.upsert_pending(second_id, f"task_b_{unique_id}", namespace_id, "b.txt")
    _ = await DocumentProcessingStatus.upsert_pending(
        foreign_id, f"task_c_{unique_id}", other_namespace_id, "c.txt"
    )

    found = await DocumentProcessingStatus.found_by_namespace_and_document_ids(
        namespace_id,
        [first_id, second_id, foreign_id, f"missing_{unique_id}"],
    )
    assert set(found) == {first_id, second_id}
    assert found[first_id].namespace_id == namespace_id
    assert await DocumentProcessingStatus.found_by_namespace_and_document_ids(namespace_id, []) == {}


@pytest.mark.asyncio
async def test_mark_processing_moves_pending_only(unique_id: str) -> None:
    document_id = f"doc_proc_{unique_id}"
    stored = await DocumentProcessingStatus.upsert_pending(
        document_id,
        f"task_proc_{unique_id}",
        f"ns_{unique_id}",
        "proc.txt",
    )
    assert stored.status == "pending"
    await DocumentProcessingStatus.mark_processing(document_id)
    processing = await DocumentProcessingStatus.get(document_id)
    assert processing is not None
    assert processing.status == "processing"
    await DocumentProcessingStatus.mark_processing(document_id)
    again = await DocumentProcessingStatus.get(document_id)
    assert again is not None
    assert again.status == "processing"
    await DocumentProcessingStatus.mark_processing(f"missing_{unique_id}")
