"""Capability files.read: ReadFileEnvelope, page_summarizations, nested parts, extra=forbid."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from core.clients.llm.mock import MockLLM
from core.types import require_json_array, require_json_object
from tests.core.files.corpus.e2e_helpers import capability_files_read_request
from tests.core.files.corpus.manifest import POSITIVE
from tests.core.files.corpus.read_helpers import store_corpus_in_files_service
from tests.fixtures.s3 import require_s3_configured

_TEXT = "fake-text.txt"
_EMBEDDED_PDF = "pdf/embedded-images.pdf"


@pytest.mark.asyncio
@pytest.mark.timeout(180)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_files_read_page_summarizations_and_parts(
    capability_gateway_di,
    frontend_di,
    system_user_id: str,
    unique_id: str,
    mock_llm_with_queue: Callable[[list[str]], MockLLM],
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == _EMBEDDED_PDF)
    file_ref = await store_corpus_in_files_service(frontend_di, entry, unique_id=unique_id)
    assert file_ref.file_id is not None
    _ = mock_llm_with_queue(
        [
            "===PAGE 0===\nMOCK_PAGE_SUMMARY",
            "===PAGE 1===\nMOCK_PAGE_SUMMARY",
            "===PAGE 2===\nMOCK_PAGE_SUMMARY",
            "===PAGE 3===\nMOCK_PAGE_SUMMARY",
        ]
    )

    response = await capability_gateway_di.capability_registry.call(
        capability_files_read_request(
            user_id=system_user_id,
            file_ids=[file_ref.file_id],
            page_end=-1,
            extra_kwargs={
                "page_summarizations": True,
                "nested_mode": "parts",
            },
        )
    )
    assert response.status == "ok"
    body = require_json_object(response.result, "files.read.result")
    assert body["tool"] == "read_file"
    files = require_json_array(body["files"], "files")
    file_result = require_json_object(files[0], "files[0]")
    assert file_result["success"] is True
    assert file_result["page_summarizations_used"] is True
    results = require_json_array(file_result["results"], "results")
    assert results
    first = require_json_object(results[0], "results[0]")
    assert first["content_mode"] == "summary"
    assert "MOCK_PAGE_SUMMARY" in str(first["result"])
    nested = require_json_array(file_result["nested"], "nested")
    assert nested
    with_bytes = [
        item
        for item in nested
        if isinstance(require_json_object(item, "nested[]").get("bytes_b64"), str)
        and str(require_json_object(item, "nested[]")["bytes_b64"]).strip()
    ]
    assert with_bytes, "nested_mode=parts must keep bytes_b64 on nested images"


@pytest.mark.asyncio
@pytest.mark.timeout(60)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_files_read_rejects_unknown_kwarg(
    capability_gateway_di,
    frontend_di,
    system_user_id: str,
    unique_id: str,
) -> None:
    require_s3_configured()
    entry = next(e for e in POSITIVE if e.relative_path == _TEXT)
    file_ref = await store_corpus_in_files_service(frontend_di, entry, unique_id=unique_id)
    assert file_ref.file_id is not None

    with pytest.raises(ValueError, match="Extra inputs|unknown_kwarg"):
        _ = await capability_gateway_di.capability_registry.call(
            capability_files_read_request(
                user_id=system_user_id,
                file_ids=[file_ref.file_id],
                extra_kwargs={"unknown_kwarg": True},
            )
        )


@pytest.mark.asyncio
@pytest.mark.timeout(60)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_files_read_rejects_legacy_file_id(
    capability_gateway_di,
    system_user_id: str,
) -> None:
    with pytest.raises(ValueError, match="file_ids"):
        _ = await capability_gateway_di.capability_registry.call(
            capability_files_read_request(
                user_id=system_user_id,
                file_ids=["ignored"],
            ).model_copy(
                update={
                    "kwargs": {"file_id": "legacy-id"},
                }
            )
        )
