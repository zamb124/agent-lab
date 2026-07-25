"""Builtin tools: platform visualizations (.viz files)."""

from __future__ import annotations

import json
import re
from typing import ClassVar, Literal
from xml.sax.saxutils import escape

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.flows.src.files.state_file_refs import upsert_state_file
from apps.flows.src.runtime_helpers.state_utils import find_file, push_ui_event
from apps.flows.src.services.platform_facades import get_file_bytes
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.files.file_ref import FileRef
from core.files.models import FileResponse
from core.files.writer import FileWriteError, FileWriter
from core.state import ExecutionState
from core.types import JsonObject, require_json_object
from core.viz.models import (
    VIZ_CONTENT_TYPE,
    VIZ_EXTENSION,
    VizDocument,
    VizEngine,
    VizKind,
    parse_viz_document_bytes,
    resolve_viz_engine,
)

JsonDict = JsonObject

_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._\- ]+")


def _slug_filename(title: str) -> str:
    cleaned = _SAFE_FILENAME_RE.sub("_", title.strip())
    cleaned = cleaned.strip(" ._") or "visualization"
    if cleaned.lower().endswith(VIZ_EXTENSION):
        return cleaned
    return f"{cleaned}{VIZ_EXTENSION}"


def _build_viz_document(
    *,
    kind: VizKind,
    title: str,
    engine: VizEngine | None,
    source: str | None,
    option: JsonObject | None,
    spec: JsonObject | None,
) -> VizDocument:
    resolved_engine = resolve_viz_engine(kind, engine)
    if spec is not None:
        document_spec = dict(spec)
    elif resolved_engine == VizEngine.MERMAID:
        if source is None or source.strip() == "":
            raise ValueError("для mermaid нужен source или spec.source")
        document_spec = {"source": source}
    elif resolved_engine == VizEngine.ECHARTS:
        if option is None:
            raise ValueError("для echarts нужен option или spec.option")
        document_spec = {"option": option}
    else:
        raise ValueError(f"неизвестный engine={resolved_engine.value}")
    return VizDocument(
        kind=kind,
        engine=resolved_engine,
        title=title.strip(),
        spec=require_json_object(document_spec, "viz.spec"),
    )


def _viz_block(file_item: FileRef, document: VizDocument) -> JsonDict:
    return {
        "type": "viz",
        "file_id": file_item.file_id,
        "kind": document.kind.value,
        "engine": document.engine.value,
        "title": document.title,
        "spec": document.spec,
        "document": require_json_object(document.model_dump(mode="json"), "viz.document"),
    }


def _pick_state_file(
    files: list[FileRef],
    *,
    file_id: str | None,
    file_name: str | None,
) -> FileRef | None:
    fid = (file_id or "").strip()
    if fid:
        for item in files:
            if item.file_id == fid:
                return item
    return find_file(files, file_name)


async def _write_viz_file(document: VizDocument, original_name: str) -> FileResponse:
    payload = json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2)
    writer = FileWriter()
    try:
        record = await writer.write(
            content=payload,
            original_name=original_name,
            content_mode="raw",
            public=True,
        )
    except FileWriteError as exc:
        raise ValueError(str(exc)) from exc
    return FileResponse.from_record(record)


def _svg_export_markup(document: VizDocument) -> str:
    title = escape(document.title)
    kind = escape(document.kind.value)
    engine = escape(document.engine.value)
    if document.engine == VizEngine.MERMAID:
        source = document.spec.get("source")
        body = escape(source if isinstance(source, str) else "")
        content = f"<pre>{body}</pre>"
    else:
        option_json = json.dumps(document.spec.get("option"), ensure_ascii=False, indent=2)
        content = f"<pre>{escape(option_json)}</pre>"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="640">'
        f"<style>text{{font-family:system-ui,sans-serif;fill:#e2e8f0}}"
        f"pre{{font-family:ui-monospace,monospace;font-size:12px;fill:#cbd5e1}}</style>"
        f'<rect width="100%" height="100%" fill="#0f172a"/>'
        f'<text x="24" y="36" font-size="20">{title}</text>'
        f'<text x="24" y="60" font-size="12">{kind} · {engine}</text>'
        f'<foreignObject x="24" y="80" width="912" height="536">'
        f'<div xmlns="http://www.w3.org/1999/xhtml" style="color:#cbd5e1;font:12px ui-monospace,monospace;'
        f'white-space:pre-wrap;overflow:auto;height:100%">{content}</div>'
        f"</foreignObject></svg>"
    )


class CreateVizArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: VizKind = Field(..., description="chart|flowchart|gantt|sequence|timeline")
    title: str = Field(..., min_length=1, max_length=500)
    engine: VizEngine | None = Field(
        None,
        description="echarts|mermaid; если не задан — выбирается по kind",
    )
    source: str | None = Field(
        None,
        description="Mermaid DSL (flowchart/sequence/gantt). Для engine=mermaid.",
    )
    option: JsonObject | None = Field(
        None,
        description="ECharts option object. Для engine=echarts.",
    )
    spec: JsonObject | None = Field(
        None,
        description="Полный spec: mermaid {source} или echarts {option}. Альтернатива source/option.",
    )
    original_name: str | None = Field(
        None,
        description="Имя файла с .viz; если не задано — из title.",
    )

    @model_validator(mode="after")
    def _require_payload(self) -> "CreateVizArgs":
        if self.spec is None and self.source is None and self.option is None:
            raise ValueError("нужен spec, source или option")
        return self


class UpdateVizArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str = Field(..., min_length=1)
    title: str | None = Field(None, min_length=1, max_length=500)
    source: str | None = None
    option: JsonObject | None = None
    spec: JsonObject | None = None

    @model_validator(mode="after")
    def _require_patch(self) -> "UpdateVizArgs":
        if self.title is None and self.source is None and self.option is None and self.spec is None:
            raise ValueError("нужен хотя бы один patch: title/source/option/spec")
        return self


class ExportVizArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str = Field(..., min_length=1)
    format: Literal["svg", "json"] = Field(
        "svg",
        description="svg — экспорт с заголовком/содержимым; json — копия .viz JSON",
    )


class VizOpenFileArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_id: str | None = None
    file_name: str | None = None

    @model_validator(mode="after")
    def _require_ref(self) -> "VizOpenFileArgs":
        if not self.file_id and not self.file_name:
            raise ValueError("file_id or file_name is required")
        return self


@tool(
    name="create_viz",
    description=(
        "Создаёт visualization файл .viz (FileRecord) и возвращает files[] + blocks[type=viz] "
        "для inline preview в чате и открытия через Documents viewer (handler=viz). "
        "flowchart/sequence/gantt → Mermaid source; chart/timeline → ECharts option."
    ),
    tags=["viz"],
    parameters_model=CreateVizArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def create_viz(
    kind: VizKind,
    title: str,
    engine: VizEngine | None = None,
    source: str | None = None,
    option: JsonObject | None = None,
    spec: JsonObject | None = None,
    original_name: str | None = None,
    *,
    state: ExecutionState,
) -> JsonDict:
    try:
        document = _build_viz_document(
            kind=kind,
            title=title,
            engine=engine,
            source=source,
            option=option,
            spec=spec,
        )
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    name = original_name.strip() if original_name and original_name.strip() else _slug_filename(document.title)
    if not name.lower().endswith(VIZ_EXTENSION):
        name = f"{name}{VIZ_EXTENSION}"
    try:
        response = await _write_viz_file(document, name)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    file_item = FileRef.from_response(response)
    upsert_state_file(state, file_item)
    _ = push_ui_event(
        state,
        event_type="files.added",
        payload={"files": [file_item.to_json_object()]},
        source="viz",
        correlation_id=response.file_id,
    )
    return {
        "success": True,
        "file": file_item.to_json_object(),
        "files": [file_item.to_json_object()],
        "blocks": [_viz_block(file_item, document)],
        "content_type": VIZ_CONTENT_TYPE,
    }


@tool(
    name="update_viz",
    description=(
        "Обновляет .viz: читает существующий file_id, патчит title/spec, создаёт новую версию FileRecord "
        "и обновляет state.files[]. Возвращает files[] + blocks[type=viz]."
    ),
    tags=["viz"],
    parameters_model=UpdateVizArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def update_viz(
    file_id: str,
    title: str | None = None,
    source: str | None = None,
    option: JsonObject | None = None,
    spec: JsonObject | None = None,
    *,
    state: ExecutionState,
) -> JsonDict:
    item = _pick_state_file(list(state.files), file_id=file_id, file_name=None)
    if item is None or not item.file_id:
        return {"success": False, "error": f"Файл file_id={file_id} не найден в state.files"}
    try:
        raw_bytes = await get_file_bytes(item.file_id)
        current = parse_viz_document_bytes(raw_bytes)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    next_title = title.strip() if title and title.strip() else current.title
    if spec is not None:
        next_spec = dict(spec)
    else:
        next_spec = dict(current.spec)
        if source is not None:
            next_spec["source"] = source
        if option is not None:
            next_spec["option"] = option
    try:
        document = VizDocument(
            kind=current.kind,
            engine=current.engine,
            title=next_title,
            spec=require_json_object(next_spec, "viz.spec"),
        )
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    try:
        response = await _write_viz_file(document, item.original_name or _slug_filename(document.title))
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    file_item = FileRef.from_response(response)
    upsert_state_file(state, file_item)
    _ = push_ui_event(
        state,
        event_type="files.added",
        payload={"files": [file_item.to_json_object()]},
        source="viz",
        correlation_id=response.file_id,
    )
    return {
        "success": True,
        "previous_file_id": item.file_id,
        "file": file_item.to_json_object(),
        "files": [file_item.to_json_object()],
        "blocks": [_viz_block(file_item, document)],
    }


@tool(
    name="export_viz",
    description=(
        "Экспортирует .viz в SVG (с заголовком и содержимым) или JSON-копию. "
        "PNG интерактивного графика — через Export в Documents viewer (ECharts canvas)."
    ),
    tags=["viz"],
    parameters_model=ExportVizArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def export_viz(
    file_id: str,
    format: Literal["svg", "json"] = "svg",
    *,
    state: ExecutionState,
) -> JsonDict:
    item = _pick_state_file(list(state.files), file_id=file_id, file_name=None)
    target_id = item.file_id if item is not None and item.file_id else file_id.strip()
    if not target_id:
        return {"success": False, "error": "file_id обязателен"}
    try:
        raw_bytes = await get_file_bytes(target_id)
        document = parse_viz_document_bytes(raw_bytes)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    base_name = _slug_filename(document.title).removesuffix(VIZ_EXTENSION)
    if format == "json":
        content = json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2)
        out_name = f"{base_name}.json"
        content_mode: Literal["raw"] = "raw"
    else:
        content = _svg_export_markup(document)
        out_name = f"{base_name}.svg"
        content_mode = "raw"
    writer = FileWriter()
    try:
        record = await writer.write(
            content=content,
            original_name=out_name,
            content_mode=content_mode,
            public=True,
        )
    except FileWriteError as exc:
        return {"success": False, "error": str(exc)}
    response = FileResponse.from_record(record)
    file_item = FileRef.from_response(response)
    upsert_state_file(state, file_item)
    _ = push_ui_event(
        state,
        event_type="files.added",
        payload={"files": [file_item.to_json_object()]},
        source="viz",
        correlation_id=response.file_id,
    )
    return {
        "success": True,
        "format": format,
        "source_file_id": target_id,
        "file": file_item.to_json_object(),
        "files": [file_item.to_json_object()],
    }


@tool(
    name="viz_open_file",
    description=(
        "Подтверждает, что .viz файл из state.files готов к открытию в Documents viewer "
        "(openFile → handler=viz). Возвращает file + blocks[type=viz] для chat panel."
    ),
    tags=["viz"],
    parameters_model=VizOpenFileArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def viz_open_file(
    file_id: str | None = None,
    file_name: str | None = None,
    *,
    state: ExecutionState,
) -> JsonDict:
    item = _pick_state_file(list(state.files), file_id=file_id, file_name=file_name)
    if item is None or not item.file_id:
        return {
            "success": False,
            "error": f"Файл не найден. Доступные: {[file_ref.original_name for file_ref in state.files]}",
        }
    try:
        raw_bytes = await get_file_bytes(item.file_id)
        document = parse_viz_document_bytes(raw_bytes)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    return {
        "success": True,
        "file": item.to_json_object(),
        "files": [item.to_json_object()],
        "blocks": [_viz_block(item, document)],
        "content_type": VIZ_CONTENT_TYPE,
    }
