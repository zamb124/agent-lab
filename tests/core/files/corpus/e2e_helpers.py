"""E2E helpers: capability files.read и read_file tool на корпусе example-docs."""

from __future__ import annotations

from dataclasses import dataclass

from apps.flows.src.state import ExecutionState
from core.capabilities import (
    CapabilityCallRequest,
    CapabilityExecutionContext,
    CapabilityExecutionTokenClaims,
    execution_token_exp,
    issue_execution_token,
)
from core.files.file_ref import FileRef
from core.files.reader.models import FileReadKind, ReadLane
from core.types import JsonObject, JsonValue, require_json_array, require_json_object
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
    file_ids: list[str],
    page_end: int = -1,
    vision_prompt: str | None = None,
    transcription_company_id: str | None = None,
    extra_kwargs: JsonObject | None = None,
) -> CapabilityCallRequest:
    if not file_ids:
        raise ValueError("file_ids must be non-empty")
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
    kwargs: JsonObject = {
        "file_ids": file_ids,
        "page_end": page_end,
    }
    if vision_prompt:
        kwargs["vision_prompt"] = vision_prompt
    if transcription_company_id:
        kwargs["transcription_company_id"] = transcription_company_id
    if extra_kwargs is not None:
        kwargs.update(extra_kwargs)
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
        kwargs=kwargs,
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


def _joined_file_result_text(file_result: JsonObject) -> str:
    page_results = require_json_array(file_result["results"], "FileResult.results")
    return "\n".join(
        str(require_json_object(page_result, "PageResult")["result"])
        for page_result in page_results
    )


def assert_files_read_envelope_body(
    body: JsonObject,
    *,
    entry: CorpusFile,
    file_ref: FileRef,
) -> JsonObject:
    """Проверяет ReadFileEnvelope от capability files.read / tool read_file."""
    assert body["success"] is True
    assert body["tool"] == "read_file"
    files = require_json_array(body["files"], "ReadFileEnvelope.files")
    assert len(files) == 1
    file_result = require_json_object(files[0], "ReadFileEnvelope.files[0]")
    assert file_result["success"] is True
    assert file_result["file_id"] == file_ref.file_id
    assert file_result["file_name"] == file_ref.original_name
    assert file_result["kind"] == entry.expected_kind.value

    pages_total_raw: JsonValue = file_result["pages_total"]
    assert isinstance(pages_total_raw, int)
    assert pages_total_raw >= entry.expected_min_pages

    page_layout = require_json_object(file_result["page_layout"], "page_layout")
    layout_total = page_layout["pages_total"]
    assert isinstance(layout_total, int)
    assert layout_total >= entry.expected_min_pages

    joined_text = _joined_file_result_text(file_result)
    if not entry.allows_empty_text:
        assert len(joined_text.strip()) > 0, (
            f"{entry.relative_path}: пустой текст после files.read"
        )

    if entry.expected_text_substring:
        assert entry.expected_text_substring in joined_text

    read_lane = file_result["read_lane"]
    if entry.uses_vision_llm:
        assert read_lane in (ReadLane.HYBRID.value, ReadLane.VISION.value)
    elif entry.uses_mock_stt_tier:
        assert read_lane == ReadLane.STT.value
    elif entry.expected_kind == FileReadKind.PDF:
        assert read_lane in (ReadLane.TEXT.value, ReadLane.HYBRID.value)
    elif entry.expected_kind == FileReadKind.IMAGE:
        assert read_lane in (ReadLane.VISION.value, ReadLane.HYBRID.value)
    return file_result
