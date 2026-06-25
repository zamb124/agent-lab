"""Auto path builders for DocsPlacement."""

from __future__ import annotations

from core.documents.placement import DocsPlacementAnchor
from core.utils.subdomain import slugify


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
        flow_label = anchor.flow_slug if anchor.flow_slug else anchor.flow_id
        if not flow_label:
            raise ValueError("flow_slug or flow_id required for flow_session placement")
        return ["Flows", slugify(flow_label), anchor.session_id]
    if kind == "work_item":
        if not anchor.work_item_id:
            raise ValueError("work_item_id required for work_item placement")
        return ["Tasks", anchor.work_item_id]
    if kind == "sync_channel_message":
        if not anchor.channel_id:
            raise ValueError("channel_id required for sync_channel_message placement")
        return ["Sync", "channels", anchor.channel_id, "attachments"]
    if kind == "rag_namespace":
        if not anchor.namespace_id:
            raise ValueError("namespace_id required for rag_namespace placement")
        return ["RAG", anchor.namespace_id]
    if kind == "manual":
        raise ValueError("manual placement requires explicit path_segments on DocsPlacement")
    raise ValueError(f"unsupported DocsPlacementAnchor.source_kind: {kind}")
