"""E2E helpers: capability files.read и read_file tool на корпусе example-docs."""

from __future__ import annotations

from dataclasses import dataclass

from core.capabilities import (
    CapabilityCallRequest,
    CapabilityExecutionContext,
    CapabilityExecutionTokenClaims,
    execution_token_exp,
    issue_execution_token,
)
from core.files.checksum import compute_content_checksum_sha256
from core.files.file_ref import FileRef
from core.files.reader.models import FileReadKind, ReadLane
from core.state import ExecutionState
from core.types import JsonObject, require_json_object
from tests.core.files.corpus.helpers import corpus_stt_company_id
from tests.core.files.corpus.manifest import CorpusFile


@dataclass(frozen=True)
class CorpusReadKwargs:
    page_end: int
    vision_prompt: str | None
    transcription_company_id: str | None


def capability_files_read_request(
    *,
    user_id: str,
    file_id: str,
    page_end: int = -1,
    vision_prompt: str | None = None,
    transcription_company_id: str | None = None,
) -> CapabilityCallRequest:
    claims = CapabilityExecutionTokenClaims(
        company_id="system",
        user_id=user_id,
        flow_id="files_read_e2e_flow",
        branch_id="main",
        session_id="files_read_e2e_flow:ctx",
        task_id="files_read_e2e_task",
        context_id="ctx",
        channel="a2a",
        request_id="files-read-e2e",
        exp=execution_token_exp(300),
    )
    return CapabilityCallRequest(
        context=CapabilityExecutionContext(
            execution_token=issue_execution_token(claims),
            company_id=claims.company_id,
            user_id=claims.user_id,
            flow_id=claims.flow_id,
            branch_id=claims.branch_id,
            session_id=claims.session_id,
            task_id=claims.task_id,
            context_id=claims.context_id,
            channel=claims.channel,
            request_id=claims.request_id,
            trace_id="files-read-e2e-trace",
        ),
        name="files.read",
        kwargs={
            "file_id": file_id,
            "page_end": page_end,
            **({"vision_prompt": vision_prompt} if vision_prompt else {}),
            **(
                {"transcription_company_id": transcription_company_id}
                if transcription_company_id
                else {}
            ),
        },
    )


def execution_state_for_files(*, files: list[FileRef], user_id: str) -> ExecutionState:
    return ExecutionState.create(
        task_id="files_read_e2e_task",
        context_id="ctx",
        user_id=user_id,
        session_id="files_read_e2e_flow:ctx",
        files=files,
    )


def read_file_kwargs_for_entry(entry: CorpusFile, *, unique_id: str) -> CorpusReadKwargs:
    vision_prompt: str | None = None
    if entry.uses_vision_llm:
        vision_prompt = "Опиши содержимое изображения."
    transcription_company_id: str | None = None
    if entry.uses_mock_stt_tier:
        transcription_company_id = corpus_stt_company_id(unique_id)
    return CorpusReadKwargs(
        page_end=-1,
        vision_prompt=vision_prompt,
        transcription_company_id=transcription_company_id,
    )


def assert_file_extract_body(
    body: JsonObject,
    *,
    entry: CorpusFile,
    file_ref: FileRef,
    raw: bytes,
) -> None:
    assert body["file_id"] == file_ref.file_id
    assert body["file_name"] == file_ref.original_name
    assert body["kind"] == entry.expected_kind.value

    pages = body["pages"]
    assert isinstance(pages, list)
    assert len(pages) >= entry.expected_min_pages

    page_layout = require_json_object(body["page_layout"], "page_layout")
    pages_total_raw = page_layout["pages_total"]
    assert isinstance(pages_total_raw, int)
    pages_total = pages_total_raw
    assert pages_total == len(pages)
    assert pages_total >= entry.expected_min_pages

    joined_text = "\n".join(
        str(require_json_object(page, "page")["text"]) for page in pages
    )
    if not entry.allows_empty_text:
        assert len(joined_text.strip()) > 0, (
            f"{entry.relative_path}: пустой текст после files.read"
        )

    if entry.expected_text_substring:
        assert entry.expected_text_substring in joined_text

    source_checksum = body.get("source_checksum")
    assert source_checksum == compute_content_checksum_sha256(raw)

    read_lane = body["read_lane"]
    if entry.uses_vision_llm:
        if entry.expected_kind == FileReadKind.PDF:
            assert read_lane in (ReadLane.HYBRID.value, ReadLane.VISION.value)
        else:
            assert read_lane == ReadLane.VISION.value
    elif entry.uses_mock_stt_tier:
        assert read_lane == ReadLane.STT.value
    elif entry.expected_kind == FileReadKind.PDF and not entry.uses_vision_llm:
        assert read_lane in (ReadLane.TEXT.value, ReadLane.HYBRID.value)
    elif entry.expected_kind == FileReadKind.IMAGE:
        assert read_lane == ReadLane.VISION.value
