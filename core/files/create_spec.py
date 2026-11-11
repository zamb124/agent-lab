"""File create contract — единственный вход в FilesService."""

from __future__ import annotations

from enum import StrEnum

from pydantic import model_validator

from core.documents.names import validate_relative_dir
from core.documents.placement import DocumentPlacement
from core.files.retention import FileRetentionSpec
from core.models.base import StrictBaseModel
from core.types import JsonObject


class FileSourceKind(StrEnum):
    CRM_ENTITY = "crm_entity"
    FLOW_SESSION = "flow_session"
    FLOW_ASSET = "flow_asset"
    WORK_ITEM = "work_item"
    SYNC_MESSAGE = "sync_message"
    SYNC_CALL_RECORDING = "sync_call_recording"
    SYNC_SPEECH_SEGMENT = "sync_speech_segment"
    SYNC_CHANNEL_ASSET = "sync_channel_asset"
    BROWSER_ARTIFACT = "browser_artifact"
    RAG_DOCUMENT = "rag_document"
    OFFICE_DOCUMENT = "office_document"
    CALENDAR_EVENT = "calendar_event"
    MAIL_MESSAGE = "mail_message"
    WIKI_PAGE = "wiki_page"
    CODE_AGENT_SOURCE = "code_agent_source"
    PLATFORM_AUXILIARY = "platform_auxiliary"
    GENERATED_EPHEMERAL = "generated_ephemeral"
    PRODUCT = "product"


# Sentinel flow_id для файлов, которые пишет сам runtime-процесс
# (FileWriter process defaults), а не конкретный flow.
RUNTIME_FLOW_ID = "runtime"


class FileSourceRef(StrictBaseModel):
    entity_id: str | None = None
    entity_type: str | None = None
    entity_title: str | None = None
    flow_id: str | None = None
    flow_slug: str | None = None
    session_id: str | None = None
    work_item_id: str | None = None
    work_queue_id: str | None = None
    board_id: str | None = None
    channel_id: str | None = None
    message_id: str | None = None
    call_id: str | None = None
    recording_id: str | None = None
    namespace_id: str | None = None
    event_id: str | None = None
    mailbox_binding_id: str | None = None
    mail_uid: str | None = None
    mailbox_email: str | None = None
    mail_subject: str | None = None
    browser_session_id: str | None = None
    import_id: str | None = None
    wiki_page_id: str | None = None
    node_id: str | None = None
    relative_dir: str | None = None
    shop_id: str | None = None
    product_id: str | None = None


class FilePostCreate(StrictBaseModel):
    rag_index_namespace: str | None = None
    rag_metadata: JsonObject | None = None
    is_public: bool = False


class FileCreateSpec(StrictBaseModel):
    source_kind: FileSourceKind
    source_ref: FileSourceRef
    retention: FileRetentionSpec
    placement: DocumentPlacement | None = None
    post_create: FilePostCreate | None = None
    metadata: JsonObject | None = None
    tags: list[str] | None = None

    @model_validator(mode="after")
    def _validate_source_ref(self) -> FileCreateSpec:
        ref = self.source_ref
        kind = self.source_kind
        if kind is FileSourceKind.CRM_ENTITY:
            if not ref.entity_id:
                raise ValueError(f"source_ref.entity_id required for {kind}")
        if kind is FileSourceKind.OFFICE_DOCUMENT and self.placement is None:
            raise ValueError("placement is required for office_document")
        if kind == FileSourceKind.RAG_DOCUMENT:
            if not ref.namespace_id:
                raise ValueError("source_ref.namespace_id required for rag_document")
        if kind == FileSourceKind.FLOW_SESSION:
            if not ref.session_id:
                raise ValueError("source_ref.session_id required for flow_session")
            if not ref.flow_id and not ref.flow_slug:
                raise ValueError("source_ref.flow_id or flow_slug required for flow_session")
        if kind == FileSourceKind.FLOW_ASSET:
            if not ref.flow_id and not ref.flow_slug:
                raise ValueError("source_ref.flow_id or flow_slug required for flow_asset")
        if kind == FileSourceKind.BROWSER_ARTIFACT:
            if not ref.browser_session_id:
                raise ValueError("source_ref.browser_session_id required for browser_artifact")
        if kind == FileSourceKind.SYNC_MESSAGE:
            if not ref.channel_id:
                raise ValueError("source_ref.channel_id required for sync_message")
        if kind == FileSourceKind.SYNC_CHANNEL_ASSET:
            if not ref.channel_id:
                raise ValueError("source_ref.channel_id required for sync_channel_asset")
        if kind == FileSourceKind.SYNC_CALL_RECORDING:
            if not ref.call_id:
                raise ValueError("source_ref.call_id required for sync_call_recording")
        if kind == FileSourceKind.SYNC_SPEECH_SEGMENT:
            if not ref.call_id:
                raise ValueError("source_ref.call_id required for sync_speech_segment")
        if kind == FileSourceKind.WORK_ITEM:
            if not ref.work_item_id:
                raise ValueError("source_ref.work_item_id required for work_item")
        if kind == FileSourceKind.CALENDAR_EVENT:
            if not ref.event_id:
                raise ValueError("source_ref.event_id required for calendar_event")
        if kind == FileSourceKind.MAIL_MESSAGE:
            if not ref.mailbox_binding_id or not ref.mail_uid:
                raise ValueError(
                    "source_ref.mailbox_binding_id and mail_uid required for mail_message"
                )
            if not ref.mailbox_email or not ref.mailbox_email.strip():
                raise ValueError("source_ref.mailbox_email required for mail_message")
        if kind == FileSourceKind.WIKI_PAGE:
            if not ref.wiki_page_id or not ref.wiki_page_id.strip():
                raise ValueError("source_ref.wiki_page_id required for wiki_page")
            if not ref.namespace_id or not ref.namespace_id.strip():
                raise ValueError("source_ref.namespace_id required for wiki_page")
        if kind == FileSourceKind.CODE_AGENT_SOURCE:
            if not ref.flow_id and not ref.flow_slug:
                raise ValueError("source_ref.flow_id or flow_slug required for code_agent_source")
            if not ref.node_id or not ref.node_id.strip():
                raise ValueError("source_ref.node_id required for code_agent_source")
            if ref.relative_dir is not None and ref.relative_dir.strip():
                _ = validate_relative_dir(ref.relative_dir)
        if kind == FileSourceKind.PRODUCT:
            if not (ref.product_id or ref.shop_id):
                raise ValueError(
                    "source_ref.product_id or shop_id required for product"
                )
        return self
