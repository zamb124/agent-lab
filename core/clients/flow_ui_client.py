"""Flow UI SDK поверх A2A 1.0 — тот же контракт, что у ``flow-ui-client.js``.

``open`` читает ``GET .../interface`` и фиксирует ``context_id`` (клиент выбирает его сам, как в
браузере); ``send`` — один ход пользователя: ``text`` Part с файлами либо ровно один ``data`` Part
``application/vnd.platform.ui-action+json``; ``cancel`` — ``CancelTask``; ``events`` раскладывает
артефакты Task по mediaType в типизированные события и сворачивает ``state`` (snapshot + JSON Patch).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Annotated, Literal

import httpx
from pydantic import Field, TypeAdapter

from core.clients.a2a_client import A2AClient, A2AClientError, A2ATaskResult
from core.flow_ui.interface import FlowInterfaceResponse
from core.flow_ui.projection import apply_json_patch
from core.flow_ui.protocol import (
    FLOW_UI_ACTION_MEDIA_TYPE,
    FLOW_UI_MEDIA_TYPE,
    FLOW_UI_OUTPUT_MEDIA_TYPES,
    JSON_MEDIA_TYPE,
    JSON_PATCH_MEDIA_TYPE,
    STATE_ARTIFACT_ID,
    UI_ARTIFACT_ID,
    FlowUIActionMessage,
    FlowUIEvent,
    FlowUINavigate,
    FlowUIRender,
    JsonPatchOperation,
)
from core.http import get_httpx_client
from core.models.base import StrictBaseModel
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

DEFAULT_BRANCH_ID = "default"


class FlowUIStateEvent(StrictBaseModel):
    """Свёрнутый ``state`` после очередного Part артефакта ``state``."""

    kind: Literal["state"] = "state"
    state: JsonObject


class FlowUITextEvent(StrictBaseModel):
    """Текстовый артефакт целиком (``response``, ``reasoning`` или авторское имя)."""

    kind: Literal["text"] = "text"
    name: str
    text: str


class FlowUIDataEvent(StrictBaseModel):
    """``data`` Part без mediaType платформенного артефакта (``tool_call:*``, ``node_start`` и т.п.)."""

    kind: Literal["data"] = "data"
    name: str
    data: JsonValue


class FlowUIFileEvent(StrictBaseModel):
    """Файловый Part артефакта: платформа отдаёт файлы только по ``url``."""

    kind: Literal["file"] = "file"
    name: str
    url: str
    media_type: str
    filename: str


FlowUITaskEvent = Annotated[
    FlowUIStateEvent
    | FlowUITextEvent
    | FlowUIDataEvent
    | FlowUIFileEvent
    | FlowUIRender
    | FlowUINavigate,
    Field(discriminator="kind"),
]

_UI_EVENT_ADAPTER: TypeAdapter[FlowUIEvent] = TypeAdapter(FlowUIEvent)
_PATCH_ADAPTER: TypeAdapter[list[JsonPatchOperation]] = TypeAdapter(list[JsonPatchOperation])


class FlowUIClientError(Exception):
    """Нарушение протокола Flow UI в Task или неверное использование клиента."""


def normalize_branch_id(branch_id: str) -> str:
    """Ветка графа ``base`` в A2A и control plane называется ``default``."""
    stripped = branch_id.strip()
    if stripped == "" or stripped == "base":
        return DEFAULT_BRANCH_ID
    return stripped


def a2a_endpoint_url(base_url: str, flow_id: str) -> str:
    """``{base_url}/api/v1/{flow_id}`` — JSON-RPC A2A и корень ``/interface``."""
    root = base_url.strip().rstrip("/")
    if root == "":
        raise FlowUIClientError("base_url is required")
    if flow_id.strip() == "":
        raise FlowUIClientError("flow_id is required")
    return f"{root}/api/v1/{flow_id.strip()}"


def interface_url(base_url: str, flow_id: str, branch_id: str) -> str:
    branch = normalize_branch_id(branch_id)
    query = "" if branch == DEFAULT_BRANCH_ID else f"?branch_id={branch}"
    return f"{a2a_endpoint_url(base_url, flow_id)}/interface{query}"


def _artifact_parts(artifact: JsonObject) -> list[JsonObject]:
    parts = artifact.get("parts")
    if not isinstance(parts, list):
        raise FlowUIClientError("artifact.parts must be a list")
    return [require_json_object(part, "artifact.parts[]") for part in parts]


def _task_artifacts(task: JsonObject) -> list[JsonObject]:
    artifacts = task.get("artifacts")
    if artifacts is None:
        return []
    if not isinstance(artifacts, list):
        raise FlowUIClientError("task.artifacts must be a list")
    return [require_json_object(artifact, "task.artifacts[]") for artifact in artifacts]


def _artifact_name(artifact: JsonObject) -> str:
    name = artifact.get("name")
    if isinstance(name, str) and name != "":
        return name
    artifact_id = artifact.get("artifactId")
    if not isinstance(artifact_id, str) or artifact_id == "":
        raise FlowUIClientError("artifact requires artifactId")
    return artifact_id


def _part_media_type(part: JsonObject) -> str:
    media_type = part.get("mediaType")
    if media_type is None:
        return ""
    if not isinstance(media_type, str):
        raise FlowUIClientError("Part.mediaType must be a string")
    return media_type


def _part_string(part: JsonObject, key: str) -> str:
    value = part.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise FlowUIClientError(f"Part.{key} must be a string")
    return value


def decode_task_events(task: JsonObject) -> list[FlowUITaskEvent]:
    """Артефакты Task в порядке появления, тот же разбор Parts, что у ``parts.js``.

    ``state`` сворачивается (snapshot + JSON Patch), ``ui`` типизируется в render/navigate;
    у остальных артефактов ``text`` Parts склеиваются в один текст, ``url`` Part — файл,
    ``data`` Part без mediaType — JSON платформенного артефакта.
    """
    events: list[FlowUITaskEvent] = []
    state: JsonObject | None = None
    for artifact in _task_artifacts(task):
        artifact_id = artifact.get("artifactId")
        parts = _artifact_parts(artifact)
        if artifact_id == STATE_ARTIFACT_ID:
            for part in parts:
                media_type = _part_media_type(part)
                if media_type == JSON_MEDIA_TYPE:
                    state = dict(require_json_object(part.get("data"), "state snapshot"))
                elif media_type == JSON_PATCH_MEDIA_TYPE:
                    if state is None:
                        raise FlowUIClientError("JSON Patch before state snapshot")
                    state = apply_json_patch(
                        state, _PATCH_ADAPTER.validate_python(part.get("data"))
                    )
                else:
                    raise FlowUIClientError(f"unexpected state part mediaType {media_type!r}")
                events.append(FlowUIStateEvent(state=state))
            continue
        if artifact_id == UI_ARTIFACT_ID:
            for part in parts:
                if _part_media_type(part) != FLOW_UI_MEDIA_TYPE:
                    raise FlowUIClientError(f"ui artifact part must be {FLOW_UI_MEDIA_TYPE}")
                events.append(_UI_EVENT_ADAPTER.validate_python(part.get("data")))
            continue
        name = _artifact_name(artifact)
        chunks: list[str] = []
        for part in parts:
            text = part.get("text")
            if isinstance(text, str):
                chunks.append(text)
                continue
            url = part.get("url")
            if isinstance(url, str):
                events.append(
                    FlowUIFileEvent(
                        name=name,
                        url=url,
                        media_type=_part_media_type(part),
                        filename=_part_string(part, "filename"),
                    )
                )
                continue
            if "raw" in part:
                raise FlowUIClientError(f"artifact {name!r} file part requires url")
            if "data" not in part:
                raise FlowUIClientError(f"artifact {name!r} Part has neither text, url nor data")
            media_type = _part_media_type(part)
            if media_type != "":
                raise FlowUIClientError(
                    f"artifact {name!r} data Part carries unexpected mediaType {media_type!r}"
                )
            events.append(FlowUIDataEvent(name=name, data=part["data"]))
        if chunks:
            events.append(FlowUITextEvent(name=name, text="".join(chunks)))
    return events


def task_state(task: JsonObject) -> JsonObject:
    """Итоговый ``state`` Task; отсутствие артефакта ``state`` — нарушение протокола."""
    state: JsonObject | None = None
    for event in decode_task_events(task):
        if isinstance(event, FlowUIStateEvent):
            state = event.state
    if state is None:
        raise FlowUIClientError("task has no state artifact")
    return state


def task_text(task: JsonObject, name: str) -> str:
    """Текст всех артефактов с данным ``name`` подряд (потоковые чанки одного текста)."""
    return "".join(
        event.text
        for event in decode_task_events(task)
        if isinstance(event, FlowUITextEvent) and event.name == name
    )


def task_ui_events(task: JsonObject) -> list[FlowUIEvent]:
    return [
        event
        for event in decode_task_events(task)
        if isinstance(event, FlowUIRender | FlowUINavigate)
    ]


class FlowUIClient:
    """Сессия одного ``context_id`` с flow: ``open`` → ``send``/``cancel`` → ``events``."""

    def __init__(
        self,
        base_url: str,
        *,
        flow_id: str,
        branch_id: str = DEFAULT_BRANCH_ID,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url: str = base_url
        self.flow_id: str = flow_id
        self.branch_id: str = normalize_branch_id(branch_id)
        self.endpoint: str = a2a_endpoint_url(base_url, flow_id)
        self.headers: dict[str, str] = dict(headers or {})
        self.timeout: float = timeout
        self.a2a: A2AClient = A2AClient(timeout=timeout)
        self.context_id: str | None = None
        self.interface: FlowInterfaceResponse | None = None
        self.tasks: list[JsonObject] = []

    async def open(self, *, context_id: str | None = None) -> FlowInterfaceResponse:
        """Interface с сервера; ``context_id`` продолжает существующий контекст, иначе создаётся новый."""
        self.context_id = (
            context_id if context_id is not None and context_id != "" else str(uuid.uuid4())
        )
        url = interface_url(self.base_url, self.flow_id, self.branch_id)
        request_headers = self.a2a.build_request_headers(self.headers)
        del request_headers["Content-Type"]
        request_headers["Accept"] = "application/json"
        try:
            async with get_httpx_client(timeout=self.timeout) as client:
                response = await client.get(url, headers=request_headers)
        except httpx.HTTPError as exc:
            raise FlowUIClientError(f"HTTP error GET {url}: {exc}") from exc
        if response.status_code != 200:
            raise FlowUIClientError(f"GET {url} failed: {response.status_code} - {response.text}")
        self.interface = FlowInterfaceResponse.model_validate(
            parse_json_object(response.content, "flow interface")
        )
        return self.interface

    def _require_context(self) -> str:
        if self.context_id is None:
            raise FlowUIClientError("call open() before send()/cancel()")
        return self.context_id

    def _metadata(self, variables: JsonObject | None) -> JsonObject | None:
        metadata: JsonObject = {}
        if self.branch_id != DEFAULT_BRANCH_ID:
            metadata["branch"] = self.branch_id
        if variables:
            metadata["variables"] = dict(variables)
        return metadata if metadata else None

    async def send(
        self,
        text: str = "",
        *,
        action: FlowUIActionMessage | None = None,
        files: Sequence[JsonObject] = (),
        task_id: str | None = None,
        variables: JsonObject | None = None,
        timeout: float | None = None,
    ) -> A2ATaskResult:
        """Ход пользователя: текст с файлами либо действие блока; возвращает Task после завершения хода."""
        context_id = self._require_context()
        parts: list[JsonObject]
        if action is not None:
            if text.strip() != "" or files:
                raise FlowUIClientError("ui action cannot be combined with text or files")
            parts = [{"data": action.model_dump(), "mediaType": FLOW_UI_ACTION_MEDIA_TYPE}]
        else:
            if text.strip() == "" and not files:
                raise FlowUIClientError("send requires text, files or action")
            parts = [{"text": text}] if text != "" else []
            parts.extend(require_json_object(file_part, "files[]") for file_part in files)
        try:
            result = await self.a2a.send_message(
                self.endpoint,
                parts=parts,
                context_id=context_id,
                task_id=task_id,
                metadata=self._metadata(variables),
                headers=self.headers,
                accepted_output_modes=FLOW_UI_OUTPUT_MEDIA_TYPES,
                timeout=timeout,
            )
        except A2AClientError as exc:
            raise FlowUIClientError(str(exc)) from exc
        self._remember(result.task)
        return result

    async def cancel(self, task_id: str, *, timeout: float | None = None) -> A2ATaskResult:
        _ = self._require_context()
        try:
            result = await self.a2a.cancel_task(
                self.endpoint, task_id, headers=self.headers, timeout=timeout
            )
        except A2AClientError as exc:
            raise FlowUIClientError(str(exc)) from exc
        self._remember(result.task)
        return result

    def _remember(self, task: JsonObject) -> None:
        task_id = task.get("id")
        if not isinstance(task_id, str) or task_id == "":
            raise FlowUIClientError("Task.id is required")
        self.tasks = [known for known in self.tasks if known.get("id") != task_id]
        self.tasks.append(task)

    def events(self, task: JsonObject | None = None) -> list[FlowUITaskEvent]:
        """События Task (по умолчанию — последнего) в порядке артефактов."""
        if task is None:
            if not self.tasks:
                raise FlowUIClientError("no task yet: call send() first")
            task = self.tasks[-1]
        return decode_task_events(task)

    @property
    def state(self) -> JsonObject:
        if not self.tasks:
            raise FlowUIClientError("no task yet: call send() first")
        return task_state(self.tasks[-1])


__all__ = [
    "DEFAULT_BRANCH_ID",
    "FlowUIClient",
    "FlowUIClientError",
    "FlowUIDataEvent",
    "FlowUIFileEvent",
    "FlowUIStateEvent",
    "FlowUITaskEvent",
    "FlowUITextEvent",
    "a2a_endpoint_url",
    "decode_task_events",
    "interface_url",
    "normalize_branch_id",
    "task_state",
    "task_text",
    "task_ui_events",
]
