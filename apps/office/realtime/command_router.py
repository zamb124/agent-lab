"""Регистрация WS command-handler'ов Documents в `core.websocket`."""

from __future__ import annotations

from apps.office.container import OfficeContainer, get_office_container
from apps.office.models.api import (
    OfficeCatalogCreateRequest,
    OfficeDocumentFromFileRequest,
    OfficeDocumentsRagIndexStatusesRequest,
    OfficeEmptyCreateRequest,
    OfficeNamespaceCreateRequest,
)
from apps.office.realtime.operations import (
    OfficeCatalogAccessRotatePayload,
    OfficeCatalogAccessUpdatePayload,
    OfficeCatalogIdPayload,
    OfficeCatalogMemberAddPayload,
    OfficeCatalogMemberRemovePayload,
    OfficeCatalogRagSearchPayload,
    OfficeCatalogRagSettingsPayload,
    OfficeCatalogUpdatePayload,
    OfficeDocumentAccessRotatePayload,
    OfficeDocumentAccessUpdatePayload,
    OfficeDocumentAppendTextPayload,
    OfficeDocumentCopyPayload,
    OfficeDocumentMovePayload,
    OfficeDocumentRenamePayload,
    OfficeDocumentReplaceTextPayload,
    OfficeDocumentSearchPayload,
    OfficeDocumentShareCreatePayload,
    OfficeDocumentsListPayload,
    OfficeDocumentUpdateCellsPayload,
    OfficeEmptyPayload,
    OfficeFileIdPayload,
    op_catalogs_access,
    op_catalogs_access_rotate_link,
    op_catalogs_access_update,
    op_catalogs_create,
    op_catalogs_ensure_path,
    op_catalogs_item,
    op_catalogs_items,
    op_catalogs_list,
    op_catalogs_member_add,
    op_catalogs_member_remove,
    op_catalogs_members_list,
    op_catalogs_rag_disable,
    op_catalogs_rag_enable,
    op_catalogs_rag_rebuild,
    op_catalogs_rag_search,
    op_catalogs_rag_settings,
    op_catalogs_rag_status,
    op_catalogs_remove,
    op_catalogs_update,
    op_company_members_list,
    op_documents_access,
    op_documents_access_rotate_link,
    op_documents_access_update,
    op_documents_ai_summary,
    op_documents_append_text,
    op_documents_bind,
    op_documents_copy,
    op_documents_create_from_file,
    op_documents_deleted_list,
    op_documents_editor_session,
    op_documents_empty,
    op_documents_events_list,
    op_documents_list,
    op_documents_metadata,
    op_documents_move,
    op_documents_permanent_remove,
    op_documents_preview,
    op_documents_rag_statuses,
    op_documents_remove,
    op_documents_rename,
    op_documents_replace_text,
    op_documents_restore,
    op_documents_revision_create,
    op_documents_revisions_list,
    op_documents_search,
    op_documents_share_create,
    op_documents_shares_list,
    op_documents_update_cells,
    op_integration_status,
    op_namespaces_create,
    op_namespaces_templates,
)
from core.documents.placement import DocsEnsurePathRequest, DocsPlacement
from core.logging import get_logger
from core.namespace.operations import NamespacesListPayload, op_namespaces_list
from core.websocket import Operation, RegisteredOperation, register_service_operations

logger = get_logger(__name__)

OFFICE_OPERATIONS: dict[str, RegisteredOperation[OfficeContainer]] = {
    "office/integration/status_requested": Operation(
        payload_model=OfficeEmptyPayload, fn=op_integration_status
    ),
    "office/namespaces/list_requested": Operation(
        payload_model=NamespacesListPayload, fn=op_namespaces_list
    ),
    "office/namespaces/templates_requested": Operation(
        payload_model=OfficeEmptyPayload, fn=op_namespaces_templates
    ),
    "office/namespaces/create_requested": Operation(
        payload_model=OfficeNamespaceCreateRequest, fn=op_namespaces_create
    ),
    "office/company_members/list_requested": Operation(
        payload_model=OfficeEmptyPayload, fn=op_company_members_list
    ),
    "office/catalogs/list_requested": Operation(
        payload_model=OfficeEmptyPayload, fn=op_catalogs_list
    ),
    "office/catalogs/ensure_path_requested": Operation(
        payload_model=DocsEnsurePathRequest, fn=op_catalogs_ensure_path
    ),
    "office/catalogs/create_requested": Operation(
        payload_model=OfficeCatalogCreateRequest, fn=op_catalogs_create
    ),
    "office/catalogs/item_requested": Operation(
        payload_model=OfficeCatalogIdPayload, fn=op_catalogs_item
    ),
    "office/catalogs/items_requested": Operation(
        payload_model=OfficeCatalogIdPayload, fn=op_catalogs_items
    ),
    "office/catalogs/update_requested": Operation(
        payload_model=OfficeCatalogUpdatePayload, fn=op_catalogs_update
    ),
    "office/catalogs/remove_requested": Operation(
        payload_model=OfficeCatalogIdPayload, fn=op_catalogs_remove
    ),
    "office/catalogs/rag_enable_requested": Operation(
        payload_model=OfficeCatalogIdPayload, fn=op_catalogs_rag_enable
    ),
    "office/catalogs/rag_disable_requested": Operation(
        payload_model=OfficeCatalogIdPayload, fn=op_catalogs_rag_disable
    ),
    "office/catalogs/rag_rebuild_requested": Operation(
        payload_model=OfficeCatalogIdPayload, fn=op_catalogs_rag_rebuild
    ),
    "office/catalogs/rag_status_requested": Operation(
        payload_model=OfficeCatalogIdPayload, fn=op_catalogs_rag_status
    ),
    "office/catalogs/rag_settings_requested": Operation(
        payload_model=OfficeCatalogRagSettingsPayload, fn=op_catalogs_rag_settings
    ),
    "office/catalogs/rag_search_requested": Operation(
        payload_model=OfficeCatalogRagSearchPayload, fn=op_catalogs_rag_search
    ),
    "office/catalogs/members_list_requested": Operation(
        payload_model=OfficeCatalogIdPayload, fn=op_catalogs_members_list
    ),
    "office/catalogs/member_add_requested": Operation(
        payload_model=OfficeCatalogMemberAddPayload, fn=op_catalogs_member_add
    ),
    "office/catalogs/member_remove_requested": Operation(
        payload_model=OfficeCatalogMemberRemovePayload, fn=op_catalogs_member_remove
    ),
    "office/catalogs/access_requested": Operation(
        payload_model=OfficeCatalogIdPayload, fn=op_catalogs_access
    ),
    "office/catalogs/access_update_requested": Operation(
        payload_model=OfficeCatalogAccessUpdatePayload, fn=op_catalogs_access_update
    ),
    "office/catalogs/access_rotate_link_requested": Operation(
        payload_model=OfficeCatalogAccessRotatePayload, fn=op_catalogs_access_rotate_link
    ),
    "office/documents/list_requested": Operation(
        payload_model=OfficeDocumentsListPayload, fn=op_documents_list
    ),
    "office/documents/create_from_file_requested": Operation(
        payload_model=OfficeDocumentFromFileRequest, fn=op_documents_create_from_file
    ),
    "office/documents/bind_requested": Operation(
        payload_model=DocsPlacement, fn=op_documents_bind
    ),
    "office/documents/rag_statuses_requested": Operation(
        payload_model=OfficeDocumentsRagIndexStatusesRequest, fn=op_documents_rag_statuses
    ),
    "office/documents/empty_requested": Operation(
        payload_model=OfficeEmptyCreateRequest, fn=op_documents_empty
    ),
    "office/documents/editor_session_requested": Operation(
        payload_model=OfficeFileIdPayload, fn=op_documents_editor_session
    ),
    "office/documents/replace_text_requested": Operation(
        payload_model=OfficeDocumentReplaceTextPayload, fn=op_documents_replace_text
    ),
    "office/documents/append_text_requested": Operation(
        payload_model=OfficeDocumentAppendTextPayload, fn=op_documents_append_text
    ),
    "office/documents/update_cells_requested": Operation(
        payload_model=OfficeDocumentUpdateCellsPayload, fn=op_documents_update_cells
    ),
    "office/documents/rename_requested": Operation(
        payload_model=OfficeDocumentRenamePayload, fn=op_documents_rename
    ),
    "office/documents/remove_requested": Operation(
        payload_model=OfficeFileIdPayload, fn=op_documents_remove
    ),
    "office/documents/deleted_list_requested": Operation(
        payload_model=OfficeEmptyPayload, fn=op_documents_deleted_list
    ),
    "office/documents/restore_requested": Operation(
        payload_model=OfficeFileIdPayload, fn=op_documents_restore
    ),
    "office/documents/permanent_remove_requested": Operation(
        payload_model=OfficeFileIdPayload, fn=op_documents_permanent_remove
    ),
    "office/documents/move_requested": Operation(
        payload_model=OfficeDocumentMovePayload, fn=op_documents_move
    ),
    "office/documents/copy_requested": Operation(
        payload_model=OfficeDocumentCopyPayload, fn=op_documents_copy
    ),
    "office/documents/search_requested": Operation(
        payload_model=OfficeDocumentSearchPayload, fn=op_documents_search
    ),
    "office/documents/access_requested": Operation(
        payload_model=OfficeFileIdPayload, fn=op_documents_access
    ),
    "office/documents/access_update_requested": Operation(
        payload_model=OfficeDocumentAccessUpdatePayload, fn=op_documents_access_update
    ),
    "office/documents/access_rotate_link_requested": Operation(
        payload_model=OfficeDocumentAccessRotatePayload, fn=op_documents_access_rotate_link
    ),
    "office/documents/preview_requested": Operation(
        payload_model=OfficeFileIdPayload, fn=op_documents_preview
    ),
    "office/documents/share_create_requested": Operation(
        payload_model=OfficeDocumentShareCreatePayload, fn=op_documents_share_create
    ),
    "office/documents/shares_list_requested": Operation(
        payload_model=OfficeFileIdPayload, fn=op_documents_shares_list
    ),
    "office/documents/revisions_list_requested": Operation(
        payload_model=OfficeFileIdPayload, fn=op_documents_revisions_list
    ),
    "office/documents/revision_create_requested": Operation(
        payload_model=OfficeFileIdPayload, fn=op_documents_revision_create
    ),
    "office/documents/events_list_requested": Operation(
        payload_model=OfficeFileIdPayload, fn=op_documents_events_list
    ),
    "office/documents/metadata_requested": Operation(
        payload_model=OfficeFileIdPayload, fn=op_documents_metadata
    ),
    "office/documents/ai_summary_requested": Operation(
        payload_model=OfficeFileIdPayload, fn=op_documents_ai_summary
    ),
}


def register_office_ws_commands() -> None:
    register_service_operations(OFFICE_OPERATIONS, get_office_container)
    logger.info(
        "Documents WS command-handlers зарегистрированы (%d операций)",
        len(OFFICE_OPERATIONS),
    )
