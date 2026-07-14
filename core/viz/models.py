"""Pydantic-модели содержимого `.viz` файла."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from core.types import JsonObject

VIZ_EXTENSION = ".viz"
VIZ_CONTENT_TYPE = "application/vnd.platform.viz+json"
VIZ_MAX_BYTES = 2_000_000
VIZ_SCHEMA_VERSION: Literal[1] = 1


class VizKind(StrEnum):
    CHART = "chart"
    FLOWCHART = "flowchart"
    GANTT = "gantt"
    SEQUENCE = "sequence"
    TIMELINE = "timeline"


class VizEngine(StrEnum):
    ECHARTS = "echarts"
    MERMAID = "mermaid"


_KIND_DEFAULT_ENGINE: dict[VizKind, VizEngine] = {
    VizKind.CHART: VizEngine.ECHARTS,
    VizKind.TIMELINE: VizEngine.ECHARTS,
    VizKind.FLOWCHART: VizEngine.MERMAID,
    VizKind.SEQUENCE: VizEngine.MERMAID,
    VizKind.GANTT: VizEngine.MERMAID,
}


def resolve_viz_engine(kind: VizKind, engine: VizEngine | None) -> VizEngine:
    if engine is not None:
        return engine
    resolved = _KIND_DEFAULT_ENGINE.get(kind)
    if resolved is None:
        raise ValueError(f"нет default engine для kind={kind.value}")
    return resolved


class VizDocument(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    schema_version: Literal[1] = VIZ_SCHEMA_VERSION
    kind: VizKind
    engine: VizEngine
    title: str = Field(min_length=1, max_length=500)
    spec: JsonObject

    @model_validator(mode="after")
    def _validate_spec_for_engine(self) -> Self:
        if self.engine == VizEngine.MERMAID:
            source = self.spec.get("source")
            if not isinstance(source, str) or source.strip() == "":
                raise ValueError("viz mermaid.spec.source обязателен (непустая строка)")
            return self
        if self.engine == VizEngine.ECHARTS:
            option = self.spec.get("option")
            if not isinstance(option, dict):
                raise ValueError("viz echarts.spec.option обязателен (JSON object)")
            return self
        raise ValueError(f"неизвестный viz engine={self.engine.value}")


def parse_viz_document_bytes(payload: bytes) -> VizDocument:
    if len(payload) == 0:
        raise ValueError("viz document пуст")
    if len(payload) > VIZ_MAX_BYTES:
        raise ValueError(f"viz document превышает лимит {VIZ_MAX_BYTES} байт")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("viz document должен быть UTF-8 JSON") from exc
    try:
        return VizDocument.model_validate_json(text)
    except ValidationError as exc:
        raise ValueError(f"viz document JSON невалиден: {exc}") from exc
