"""RAG индексация scan-PDF через канонический FileReader.read (hybrid OCR)."""

from __future__ import annotations

import os
import tempfile
import uuid

import pytest

from core.files.reader.models import ReadLane
from tests.core.files.corpus.manifest import CORPUS_DIR
from tests.rag.test_pgvector_provider import (
    _upload_metadata,
    _vector_chunk_count,
    _vector_document_rows_ordered,
)


@pytest.mark.asyncio
@pytest.mark.timeout(300)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_pgvector_indexes_scanned_pdf_with_hybrid_ocr(
    rag_provider_pgvector,
    ns_name,
    rag_company_id,
    mock_llm_with_queue,
) -> None:
    pdf_path = CORPUS_DIR / "pdf/single_table.pdf"
    if not pdf_path.exists():
        pytest.skip("corpus pdf/single_table.pdf отсутствует")

    mock_llm_with_queue(["MOCK_VISION"])
    document_id = f"doc_{uuid.uuid4().hex[:12]}"
    raw = pdf_path.read_bytes()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        _ = tmp.write(raw)
        tmp_path = tmp.name

    try:
        doc = await rag_provider_pgvector.upload_document_from_file(
            ns_name,
            tmp_path,
            document_name="single_table.pdf",
            metadata=_upload_metadata(
                rag_company_id,
                {"document_id": document_id},
            ),
        )
    finally:
        os.unlink(tmp_path)

    assert doc.document_id == document_id
    chunk_count = await _vector_chunk_count(
        rag_provider_pgvector._session_factory,
        ns_name,
        rag_company_id,
    )
    assert chunk_count > 0

    rows = await _vector_document_rows_ordered(
        rag_provider_pgvector._session_factory,
        ns_name,
        document_id,
        rag_company_id,
    )
    assert len(rows) > 0
    assert rows[0].metadata_.get("file_read_lane") == ReadLane.HYBRID.value
