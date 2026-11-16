"""Модели ответов, которые CLI читает. Лишние поля API игнорируются."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from platform_sdk.json_types import JsonObject, JsonValue, require_object


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    error_code: str = ""
    error_detail: str = ""
    detail: str = ""
    error_params: JsonObject = Field(default_factory=dict)
    request_id: str | None = None
    trace_id: str | None = None
    service: str | None = None

    def resolved_detail(self, status: int) -> str:
        if self.error_detail != "":
            return self.error_detail
        if self.detail != "":
            return self.detail
        return f"HTTP {status}"

    def resolved_code(self, status: int) -> str:
        if self.error_code != "":
            return self.error_code
        if status >= 500:
            return "internal"
        return "ws_invalid_payload"


class A2AErrorBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: int | None = None
    message: str = ""
    data: JsonObject = Field(default_factory=dict)


class A2AErrorFrame(BaseModel):
    model_config = ConfigDict(extra="ignore")

    error: A2AErrorBody


class A2APart(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = ""


class A2AMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    parts: list[A2APart] = Field(default_factory=list)

    def text(self) -> str:
        chunks = [part.text for part in self.parts if part.text != ""]
        return "".join(chunks)


class A2AStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    state: str = ""
    message: A2AMessage | None = None


class A2ATask(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = ""
    contextId: str = ""
    status: A2AStatus | None = None


class A2AStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    taskId: str = ""
    contextId: str = ""
    status: A2AStatus | None = None


class A2AResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    task: A2ATask | None = None
    statusUpdate: A2AStatusUpdate | None = None


class A2AFrame(BaseModel):
    model_config = ConfigDict(extra="ignore")

    result: A2AResult | None = None
    error: A2AErrorBody | None = None


class FlowIdentity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    flow_id: str = Field(min_length=1)


class Versioned(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: str = Field(min_length=1)


class ValidateResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    valid: bool = False
    errors: list[JsonValue] = Field(default_factory=list)


class LockFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    context: str = ""
    company_subdomain: str = ""
    flow_id: str = ""
    base_version: str = ""
    files: dict[str, str] = Field(default_factory=dict)


class IdRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = ""
    suite_id: str = ""
    rubric_id: str = ""


class IdPage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[IdRow] = Field(default_factory=list)


class RubricSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    pass_threshold: float = 7


class SuiteFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    rubrics: list[RubricSpec] = Field(default_factory=list)


class RubricBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rubric_id: str = ""


class RubricCreated(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rubric_id: str = ""
    rubric: RubricBody | None = None

    def resolved_id(self) -> str:
        if self.rubric is not None and self.rubric.rubric_id != "":
            return self.rubric.rubric_id
        return self.rubric_id


class SuiteCreated(BaseModel):
    model_config = ConfigDict(extra="ignore")

    suite_id: str = Field(min_length=1)


class RunBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str = ""
    state: str = ""


class RunEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str = ""
    state: str = ""
    run: RunBody | None = None

    def resolved(self) -> RunBody:
        if self.run is not None and self.run.run_id != "":
            return self.run
        return RunBody(run_id=self.run_id, state=self.state)

    def resolved_state(self) -> str:
        if self.run is not None and "state" in self.run.model_fields_set:
            return self.run.state
        return self.state


class EvalEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sequence: int = 0
    event_type: str = ""


class EvalEventPage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[EvalEvent] = Field(default_factory=list)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str = ""
    content: str = ""


class ExecutionStateView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    messages: list[ChatMessage] = Field(default_factory=list)


class HistoryView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    events: list[JsonValue] = Field(default_factory=list)


class LogsView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[JsonValue] = Field(default_factory=list)


class NamedRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = ""
    type: str = ""


class RecordPage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[NamedRecord] = Field(default_factory=list)


class CaseLine(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = ""
    case_key: str = ""


class IndexAccepted(BaseModel):
    model_config = ConfigDict(extra="ignore")

    document_id: str = Field(min_length=1)


class DocumentStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    document_id: str = ""
    status: str = ""


class UploadConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chunk_size_bytes: int = Field(ge=1)


class UploadInit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    upload_id: str = Field(min_length=1)


class FileRef(BaseModel):
    model_config = ConfigDict(extra="allow")

    file_id: str = Field(min_length=1)


def dump(model: BaseModel) -> JsonObject:
    return require_object(model.model_dump(mode="json"), type(model).__name__)
