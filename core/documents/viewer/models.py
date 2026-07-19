"""Pydantic-модели контракта открытия документа через viewer handlers."""

from __future__ import annotations

from typing import ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.types import JsonObject

DocumentViewerHandlerId = Literal["onlyoffice", "media", "image", "text", "binary", "viz"]
MediaViewerKind = Literal["audio", "video"]
OfficeViewerScope = Literal["catalog", "file"]
TextPresentation = Literal["code", "html", "markdown"]
TextViewMode = Literal["preview", "source"]
VizViewerEngine = Literal["echarts", "mermaid"]
VizViewerKind = Literal["chart", "flowchart", "gantt", "sequence", "timeline"]


class DocumentOpenCapabilities(BaseModel):
    view: bool
    edit: bool
    preview: bool
    sync_on_close: bool
    download: bool
    server_mutations: bool


class OnlyOfficeOpenPayload(BaseModel):
    document_server_url: str
    token: str


class MediaOpenPayload(BaseModel):
    frame_url: str = ""
    stream_url: str
    content_type: str
    kind: MediaViewerKind


class ImageOpenPayload(BaseModel):
    frame_url: str = ""
    stream_url: str
    content_type: str


class TextOpenPayload(BaseModel):
    frame_url: str = ""
    stream_url: str
    save_url: str
    content_type: str
    edit_mode: bool
    max_edit_bytes: int = Field(default=512_000, ge=1)
    presentation: TextPresentation = "code"
    default_view_mode: TextViewMode = "source"

    @model_validator(mode="after")
    def presentation_matches_default_view_mode(self) -> Self:
        if self.presentation == "code" and self.default_view_mode != "source":
            raise ValueError("default_view_mode для presentation=code должен быть source")
        if self.presentation in {"html", "markdown"} and self.default_view_mode not in {
            "preview",
            "source",
        }:
            raise ValueError(
                f"default_view_mode недопустим для presentation={self.presentation}"
            )
        return self


class BinaryOpenPayload(BaseModel):
    frame_url: str = ""
    download_url: str
    content_type: str
    file_size: int = Field(ge=0)


class VizOpenPayload(BaseModel):
    stream_url: str
    content_type: str
    kind: VizViewerKind
    engine: VizViewerEngine
    title: str
    document: JsonObject


class DocumentOpenConfigResponse(BaseModel):
    handler: DocumentViewerHandlerId
    file_id: str
    title: str
    original_name: str
    content_type: str
    file_category: str
    onlyoffice_document_type: str | None = None
    download_url: str | None = None
    capabilities: DocumentOpenCapabilities
    onlyoffice: OnlyOfficeOpenPayload | None = None
    media: MediaOpenPayload | None = None
    image: ImageOpenPayload | None = None
    text: TextOpenPayload | None = None
    binary: BinaryOpenPayload | None = None
    viz: VizOpenPayload | None = None

    @model_validator(mode="after")
    def payload_matches_handler(self) -> Self:
        payload_fields: dict[DocumentViewerHandlerId, object | None] = {
            "onlyoffice": self.onlyoffice,
            "media": self.media,
            "image": self.image,
            "text": self.text,
            "binary": self.binary,
            "viz": self.viz,
        }
        active = payload_fields[self.handler]
        if active is None:
            raise ValueError(f"payload для handler={self.handler} обязателен")
        for handler_id, payload in payload_fields.items():
            if handler_id != self.handler and payload is not None:
                raise ValueError(f"payload.{handler_id} недопустим при handler={self.handler}")
        return self


class OfficeViewerStreamTokenClaims(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    typ: Literal["office_view"]
    handler: DocumentViewerHandlerId
    viewer_scope: OfficeViewerScope
    file_id: str
    company_id: str
    content_type: str
    edit_mode: bool = False
    public_link_token_hash: str | None = None
    iat: int
    exp: int


class OfficeViewerSaveTokenClaims(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    typ: Literal["office_view_save"]
    viewer_scope: OfficeViewerScope
    file_id: str
    company_id: str
    public_link_token_hash: str | None = None
    iat: int
    exp: int
