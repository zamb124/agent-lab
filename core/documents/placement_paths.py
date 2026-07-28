"""Auto path builders for DocsPlacement."""

from __future__ import annotations

from core.documents.placement import DocsPlacementAnchor
from core.utils.subdomain import slugify


def _flow_label(anchor: DocsPlacementAnchor) -> str:
    flow_label = anchor.flow_slug if anchor.flow_slug else anchor.flow_id
    if not flow_label:
        raise ValueError("flow_slug or flow_id required for flow placement")
    return slugify(flow_label)


def _mail_title_segment(anchor: DocsPlacementAnchor) -> str:
    if anchor.mail_subject and anchor.mail_subject.strip():
        return slugify(anchor.mail_subject.strip())
    if anchor.mail_uid and anchor.mail_uid.strip():
        return anchor.mail_uid.strip()
    raise ValueError("mail_subject or mail_uid required for mail_message placement")


def build_path_segments(anchor: DocsPlacementAnchor) -> list[str]:
    kind = anchor.source_kind
    if kind == "crm_entity":
        if not anchor.entity_type:
            raise ValueError("entity_type required for crm_entity placement")
        label = anchor.entity_title if anchor.entity_title else anchor.entity_id
        if not label:
            raise ValueError("entity_title or entity_id required for crm_entity placement")
        return ["Networkle", anchor.entity_type, slugify(label)]
    if kind == "flow_session":
        if not anchor.session_id:
            raise ValueError("session_id required for flow_session placement")
        return ["Flows", _flow_label(anchor), anchor.session_id]
    if kind == "flow_asset":
        return ["Flows", _flow_label(anchor)]
    if kind == "work_item":
        if not anchor.work_item_id:
            raise ValueError("work_item_id required for work_item placement")
        queue_segment = (
            anchor.work_queue_id.strip()
            if anchor.work_queue_id and anchor.work_queue_id.strip()
            else "queues"
        )
        board_segment = (
            anchor.board_id.strip() if anchor.board_id and anchor.board_id.strip() else "boards"
        )
        return ["Worktracker", queue_segment, board_segment, anchor.work_item_id]
    if kind in {"sync_message", "sync_channel_message"}:
        if not anchor.channel_id:
            raise ValueError("channel_id required for sync message placement")
        return ["Sync", anchor.channel_id]
    if kind == "sync_channel_asset":
        if not anchor.channel_id:
            raise ValueError("channel_id required for sync_channel_asset placement")
        return ["Sync", anchor.channel_id, "assets"]
    if kind == "sync_call_recording":
        if not anchor.call_id:
            raise ValueError("call_id required for sync_call_recording placement")
        return ["Sync", "calls", anchor.call_id]
    if kind == "sync_speech_segment":
        if not anchor.call_id:
            raise ValueError("call_id required for sync_speech_segment placement")
        return ["Sync", "calls", anchor.call_id, "speech"]
    if kind == "calendar_event":
        if not anchor.event_id:
            raise ValueError("event_id required for calendar_event placement")
        return ["Calendar", anchor.event_id]
    if kind in {"browser_artifact", "browser_session"}:
        if not anchor.browser_session_id:
            raise ValueError("browser_session_id required for browser placement")
        return ["Browser", anchor.browser_session_id]
    if kind in {"rag_document", "rag_namespace"}:
        if not anchor.namespace_id:
            raise ValueError("namespace_id required for rag placement")
        return ["RAG", anchor.namespace_id]
    if kind == "mail_message":
        if not anchor.mailbox_email or not anchor.mailbox_email.strip():
            raise ValueError("mailbox_email required for mail_message placement")
        return ["Mail", anchor.mailbox_email.strip(), _mail_title_segment(anchor)]
    if kind == "wiki_page":
        if not anchor.wiki_page_id or not anchor.wiki_page_id.strip():
            raise ValueError("wiki_page_id required for wiki_page placement")
        if not anchor.namespace_id or not anchor.namespace_id.strip():
            raise ValueError("namespace_id required for wiki_page placement")
        return ["Wiki", anchor.namespace_id.strip(), anchor.wiki_page_id.strip()]
    if kind == "crm_knowledge_import":
        if not anchor.import_id:
            raise ValueError("import_id required for crm_knowledge_import placement")
        return ["Networkle", "imports", anchor.import_id]
    if kind == "work_item_comment":
        if not anchor.work_item_id or not anchor.comment_id:
            raise ValueError("work_item_id and comment_id required for work_item_comment placement")
        return ["Worktracker", "queues", "boards", anchor.work_item_id, "comments", anchor.comment_id]
    if kind == "work_item_resolution":
        if not anchor.work_item_id:
            raise ValueError("work_item_id required for work_item_resolution placement")
        return ["Worktracker", "queues", "boards", anchor.work_item_id, "resolution"]
    if kind == "manual":
        raise ValueError("manual placement requires explicit path_segments on DocsPlacement")
    if kind == "office_manual":
        raise ValueError("office_manual placement requires explicit path_segments on DocsPlacement")
    raise ValueError(f"unsupported DocsPlacementAnchor.source_kind: {kind}")
