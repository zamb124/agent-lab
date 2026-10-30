"""RAGResource.add_document пишет текст и метаданные в живой индекс."""

from __future__ import annotations

import pytest

from apps.flows.di import FlowsDi
from core.db.models.rag.vector_document import VectorDocument
from core.rag.rag_resource import RAGResource
from core.types import JsonObject, require_json_object


async def _stored_metadata(namespace_id: str, document_id: str) -> JsonObject:
    chunks = await VectorDocument.objects.filter(
        namespace_id=namespace_id,
        document_id=document_id,
    ).all()
    if not chunks:
        raise AssertionError(f"vector document {document_id!r} was not stored")
    return chunks[0].metadata


def _assert_search_hit(hits: list[JsonObject], marker: str) -> None:
    for hit in hits:
        content = hit.get("content")
        if isinstance(content, str) and marker in content:
            return
    raise AssertionError(f"indexed text {marker!r} was not found")


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_add_document_stores_metadata(
    di: FlowsDi,
    rag_service: object,
    unique_id: str,
) -> None:
    _ = rag_service
    marker = f"hello-{unique_id}"
    namespace_id = f"rag_res_{unique_id}"
    document_id = f"fid-{unique_id}"
    resource = RAGResource(
        namespace=namespace_id,
        namespace_service=di.namespace_service,
    )
    added = await resource.add_document(
        document_id,
        marker,
        metadata={"tag": "t"},
        name="n.txt",
    )
    assert added["status"] == "added"
    _assert_search_hit(await resource.search(marker, top_k=3), marker)
    metadata = await _stored_metadata(namespace_id, document_id)
    assert metadata.get("tag") == "t"


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_add_document_merges_index_profile_config(
    di: FlowsDi,
    rag_service: object,
    unique_id: str,
) -> None:
    _ = rag_service
    marker = f"profile-{unique_id}"
    namespace_id = f"rag_ipc_{unique_id}"
    document_id = f"fid-{unique_id}"
    resource = RAGResource(
        namespace=namespace_id,
        namespace_service=di.namespace_service,
        index_profile_config={"split": {"chunk_size": 256}},
    )
    added = await resource.add_document(
        document_id,
        marker,
        metadata={"index_profile_config": {"split": {"strategy": "recursive"}}},
        name="n.txt",
        index_profile_config={"lexical": {"enabled": True}},
    )
    assert added["status"] == "added"
    _assert_search_hit(await resource.search(marker, top_k=3), marker)
    metadata = await _stored_metadata(namespace_id, document_id)
    index_profile = require_json_object(
        metadata.get("index_profile_config"),
        "rag.hit.index_profile_config",
    )
    split = require_json_object(index_profile.get("split"), "rag.hit.split")
    lexical = require_json_object(index_profile.get("lexical"), "rag.hit.lexical")
    assert split.get("chunk_size") == 256
    assert split.get("strategy") == "recursive"
    assert lexical.get("enabled") is True
