"""Путь источника файла в дереве Документов и якорь прав."""

from __future__ import annotations

from dataclasses import dataclass

from core.authz.models import AuthzObject
from core.authz.types import AuthzObjectType
from core.documents.names import split_catalog_path, validate_relative_dir
from core.files.create_spec import RUNTIME_FLOW_ID, FileSourceKind, FileSourceRef
from core.utils.slug import slugify


@dataclass(frozen=True, slots=True)
class SourceAnchor:
    """Каталог, с которого наследуется доступ источника. Индекс — в path."""

    index: int
    source: AuthzObject | None
    company_visible: bool


def _flow_label(source_ref: FileSourceRef) -> str:
    flow_label = source_ref.flow_slug if source_ref.flow_slug else source_ref.flow_id
    if not flow_label:
        raise ValueError("flow_slug or flow_id required for flow placement")
    slug = slugify(flow_label)
    if slug == "":
        raise ValueError(f"flow label {flow_label!r} has no slug characters")
    return slug


def _mail_title(source_ref: FileSourceRef) -> str:
    subject_slug = slugify(source_ref.mail_subject) if source_ref.mail_subject else ""
    if subject_slug != "":
        return subject_slug
    if source_ref.mail_uid and source_ref.mail_uid.strip():
        return source_ref.mail_uid.strip()
    raise ValueError("mail_subject or mail_uid required for mail_message placement")


def _require(value: str | None, message: str) -> str:
    if value is None or value.strip() == "":
        raise ValueError(message)
    return value.strip()


def source_catalog_path(source_kind: FileSourceKind, source_ref: FileSourceRef) -> list[str]:
    kind = source_kind
    if kind is FileSourceKind.CRM_ENTITY:
        entity_type = _require(source_ref.entity_type, "entity_type required for crm_entity placement")
        title_slug = slugify(source_ref.entity_title) if source_ref.entity_title else ""
        label = title_slug if title_slug != "" else source_ref.entity_id
        if not label:
            raise ValueError("entity_title or entity_id required for crm_entity placement")
        return ["Networkle", entity_type, label]
    if kind is FileSourceKind.FLOW_SESSION:
        session_id = _require(source_ref.session_id, "session_id required for flow_session placement")
        return ["Flows", _flow_label(source_ref), session_id]
    if kind is FileSourceKind.FLOW_ASSET:
        return ["Flows", _flow_label(source_ref)]
    if kind is FileSourceKind.WORK_ITEM:
        work_item_id = _require(source_ref.work_item_id, "work_item_id required for work_item placement")
        queue_segment = (
            source_ref.work_queue_id.strip()
            if source_ref.work_queue_id and source_ref.work_queue_id.strip()
            else "queues"
        )
        board_segment = (
            source_ref.board_id.strip() if source_ref.board_id and source_ref.board_id.strip() else "boards"
        )
        return ["Worktracker", queue_segment, board_segment, work_item_id]
    if kind is FileSourceKind.SYNC_MESSAGE:
        return ["Sync", _require(source_ref.channel_id, "channel_id required for sync message placement")]
    if kind is FileSourceKind.SYNC_CHANNEL_ASSET:
        channel_id = _require(source_ref.channel_id, "channel_id required for sync_channel_asset placement")
        return ["Sync", channel_id, "assets"]
    if kind is FileSourceKind.SYNC_CALL_RECORDING:
        channel_id = _require(source_ref.channel_id, "channel_id required for sync_call_recording placement")
        call_id = _require(source_ref.call_id, "call_id required for sync_call_recording placement")
        return ["Sync", channel_id, "calls", call_id]
    if kind is FileSourceKind.SYNC_SPEECH_SEGMENT:
        channel_id = _require(source_ref.channel_id, "channel_id required for sync_speech_segment placement")
        call_id = _require(source_ref.call_id, "call_id required for sync_speech_segment placement")
        return ["Sync", channel_id, "calls", call_id, "speech"]
    if kind is FileSourceKind.CALENDAR_EVENT:
        return ["Calendar", _require(source_ref.event_id, "event_id required for calendar_event placement")]
    if kind is FileSourceKind.BROWSER_ARTIFACT:
        session_id = _require(
            source_ref.browser_session_id, "browser_session_id required for browser placement"
        )
        return ["Browser", session_id]
    if kind is FileSourceKind.RAG_DOCUMENT:
        return ["RAG", _require(source_ref.namespace_id, "namespace_id required for rag placement")]
    if kind is FileSourceKind.MAIL_MESSAGE:
        mailbox = _require(source_ref.mailbox_email, "mailbox_email required for mail_message placement")
        return ["Mail", mailbox, _mail_title(source_ref)]
    if kind is FileSourceKind.WIKI_PAGE:
        namespace_id = _require(source_ref.namespace_id, "namespace_id required for wiki_page placement")
        wiki_page_id = _require(source_ref.wiki_page_id, "wiki_page_id required for wiki_page placement")
        return ["Wiki", namespace_id, wiki_page_id]
    if kind is FileSourceKind.PRODUCT:
        if source_ref.product_id:
            return ["Products", source_ref.product_id]
        shop_id = _require(source_ref.shop_id, "shop_id or product_id required for product placement")
        return ["Shop", shop_id]
    if kind is FileSourceKind.CODE_AGENT_SOURCE:
        node_id = _require(source_ref.node_id, "node_id required for code_agent_source placement")
        path = ["Flows", _flow_label(source_ref), "code_agent", node_id]
        if source_ref.relative_dir is not None and source_ref.relative_dir.strip():
            path.extend(validate_relative_dir(source_ref.relative_dir))
        return path
    raise ValueError(f"source kind {kind} has no catalog path")


def source_anchor(
    source_kind: FileSourceKind,
    source_ref: FileSourceRef,
    *,
    company_id: str,
) -> SourceAnchor:
    if source_kind is FileSourceKind.MAIL_MESSAGE:
        binding_id = _require(source_ref.mailbox_binding_id, "mailbox_binding_id required")
        return SourceAnchor(1, AuthzObject.mailbox_binding(binding_id), False)
    if source_kind in {
        FileSourceKind.SYNC_MESSAGE,
        FileSourceKind.SYNC_CHANNEL_ASSET,
        FileSourceKind.SYNC_CALL_RECORDING,
        FileSourceKind.SYNC_SPEECH_SEGMENT,
    }:
        channel_id = _require(source_ref.channel_id, "channel_id required")
        return SourceAnchor(1, AuthzObject.sync_channel(channel_id), False)
    if source_kind is FileSourceKind.CRM_ENTITY:
        entity_id = _require(source_ref.entity_id, "entity_id required")
        path = source_catalog_path(source_kind, source_ref)
        return SourceAnchor(len(path) - 1, AuthzObject.crm_entity(entity_id), False)
    if source_kind in {
        FileSourceKind.FLOW_ASSET,
        FileSourceKind.FLOW_SESSION,
        FileSourceKind.CODE_AGENT_SOURCE,
    }:
        flow_id = _require(source_ref.flow_id, "flow_id required")
        if flow_id == RUNTIME_FLOW_ID:
            return SourceAnchor(1, None, True)
        return SourceAnchor(1, AuthzObject.flow(flow_id, company_id=company_id), False)
    if source_kind is FileSourceKind.WORK_ITEM:
        if source_ref.work_queue_id and source_ref.work_queue_id.strip():
            return SourceAnchor(1, AuthzObject.work_queue(source_ref.work_queue_id.strip()), False)
        return SourceAnchor(1, None, True)
    if source_kind is FileSourceKind.WIKI_PAGE:
        wiki_page_id = _require(source_ref.wiki_page_id, "wiki_page_id required")
        path = source_catalog_path(source_kind, source_ref)
        return SourceAnchor(len(path) - 1, AuthzObject.wiki_page(wiki_page_id), False)
    if source_kind in {
        FileSourceKind.CALENDAR_EVENT,
        FileSourceKind.BROWSER_ARTIFACT,
        FileSourceKind.RAG_DOCUMENT,
        FileSourceKind.PRODUCT,
    }:
        path = source_catalog_path(source_kind, source_ref)
        return SourceAnchor(len(path) - 1, None, True)
    raise ValueError(f"source kind {source_kind} has no anchor")


def source_object_key(source: AuthzObject) -> str:
    if source.object_type not in {
        AuthzObjectType.MAILBOX_BINDING,
        AuthzObjectType.SYNC_CHANNEL,
        AuthzObjectType.CRM_ENTITY,
        AuthzObjectType.FLOW,
        AuthzObjectType.WORK_QUEUE,
        AuthzObjectType.WIKI_PAGE,
    }:
        raise ValueError(f"unsupported document source type: {source.object_type}")
    return source.fga_id


def placed_path(source_kind: FileSourceKind, source_ref: FileSourceRef) -> list[str]:
    return split_catalog_path(source_catalog_path(source_kind, source_ref))
