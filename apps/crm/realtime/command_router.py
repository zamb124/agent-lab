"""Регистрация WS command-handler'ов CRM в `core.websocket`."""

from __future__ import annotations

from apps.crm.container import CRMContainer, get_crm_container
from apps.crm.models.access_request_models import AccessRequestCreate
from apps.crm.models.api import (
    ActivityTaskCreateRequest,
    BulkCardsRequest,
    BulkCreateRequest,
    BulkDeleteRequest,
    BulkUpdateRequest,
    DailySummaryRequest,
    EntityCreate,
    EntityMergeRequest,
    EntitySearchQueryRequest,
    EntityTypeCreate,
    NamespaceCreateRequest,
    NamespaceTemplateCreateRequest,
    PeriodSummaryRequest,
    RelationshipCreate,
    RelationshipTypeCreate,
    SearchMentionsRequest,
    StartDailySummaryRequest,
    StartKnowledgeImportRequest,
    StartNoteAnalyzeRequest,
    StartPeriodSummaryRequest,
)
from apps.crm.realtime.operations import (
    CrmAccessRequestIdPayload,
    CrmAccessRequestListPayload,
    CrmAccessRequestUpdatePayload,
    CrmActivityTasksListPayload,
    CrmAttachmentsAttachPayload,
    CrmAttachmentsRemovePayload,
    CrmCompanyInitPayload,
    CrmEntitiesAggregatePayload,
    CrmEntitiesInfluenceGraphPayload,
    CrmEntitiesRelatedPayload,
    CrmEntitiesTimelineBoundsPayload,
    CrmEntityIdPayload,
    CrmEntityTypeKeyPayload,
    CrmEntityTypePublicFieldsPayload,
    CrmEntityTypesListPayload,
    CrmEntityTypeUpdatePayload,
    CrmEntityUpdatePayload,
    CrmGrantCreatePayload,
    CrmGrantIdPayload,
    CrmGrantsListPayload,
    CrmIntegrationAuthorizePayload,
    CrmIntegrationAutoNoteAiPayload,
    CrmIntegrationAutoSyncPayload,
    CrmIntegrationNamespacePayload,
    CrmIntegrationProviderPayload,
    CrmLaraSummaryPayload,
    CrmNamespaceNamePayload,
    CrmNamespaceUpdatePayload,
    CrmNoteAnalysisDraftSavePayload,
    CrmNoteIdPayload,
    CrmOffsetPagePayload,
    CrmOverviewGraphPayload,
    CrmRelationshipIdPayload,
    CrmRelationshipsListPayload,
    CrmRelationshipsPathPayload,
    CrmSuggestKeyPayload,
    CrmSuggestsListPayload,
    CrmTaskIdPayload,
    CrmTasksListPayload,
    CrmTemplateIdPayload,
    CrmTemplateTypeRemovePayload,
    CrmTemplateTypeUpsertPayload,
    CrmTemplateUpdatePayload,
    op_access_requests_create,
    op_access_requests_item,
    op_access_requests_list,
    op_access_requests_update,
    op_activity_tasks_create,
    op_activity_tasks_list,
    op_attachments_attach,
    op_attachments_list,
    op_attachments_remove,
    op_crm_company_init,
    op_entities_aggregate,
    op_entities_bulk_create,
    op_entities_bulk_delete,
    op_entities_bulk_update,
    op_entities_card,
    op_entities_cards_bulk,
    op_entities_create,
    op_entities_daily_summary,
    op_entities_exclusive_related,
    op_entities_export,
    op_entities_influence_graph,
    op_entities_item,
    op_entities_mentions_search,
    op_entities_merge,
    op_entities_overview_graph,
    op_entities_period_summary,
    op_entities_person_self,
    op_entities_query,
    op_entities_related,
    op_entities_relationships,
    op_entities_remove,
    op_entities_timeline_bounds,
    op_entities_update,
    op_entity_types_create,
    op_entity_types_item,
    op_entity_types_list,
    op_entity_types_public_fields,
    op_entity_types_update,
    op_grants_create,
    op_grants_item,
    op_grants_list,
    op_grants_remove,
    op_namespace_integrations_authorize,
    op_namespace_integrations_auto_note_ai,
    op_namespace_integrations_auto_sync,
    op_namespace_integrations_custom_fields_sync,
    op_namespace_integrations_list,
    op_namespace_integrations_sync,
    op_namespaces_create,
    op_namespaces_editability,
    op_namespaces_lara_summary,
    op_namespaces_list,
    op_namespaces_update,
    op_notes_analysis_draft_discard,
    op_notes_analysis_draft_repair,
    op_notes_analysis_draft_save,
    op_notes_analysis_error_dismiss,
    op_notes_analyze,
    op_notes_markdown_format,
    op_relationship_types_create,
    op_relationship_types_list,
    op_relationships_create,
    op_relationships_item,
    op_relationships_list,
    op_relationships_path,
    op_relationships_remove,
    op_suggests_dismiss,
    op_suggests_list,
    op_suggests_resolve,
    op_tasks_cancel,
    op_tasks_created_entities,
    op_tasks_daily_summary_start,
    op_tasks_item,
    op_tasks_knowledge_import_start,
    op_tasks_list,
    op_tasks_period_summary_start,
    op_tasks_retry,
    op_tasks_review_complete,
    op_tasks_rollback,
    op_templates_create,
    op_templates_item,
    op_templates_list,
    op_templates_remove,
    op_templates_schema_options,
    op_templates_type_remove,
    op_templates_type_upsert,
    op_templates_update,
)
from apps.crm.services.entity_export import CrmEntitiesExportPayload
from core.logging import get_logger
from core.websocket import EmptyPayload, Operation, RegisteredOperation, register_service_operations

logger = get_logger(__name__)

CRM_OPERATIONS: dict[str, RegisteredOperation[CRMContainer]] = {
    "crm/company/init_requested": Operation(
        payload_model=CrmCompanyInitPayload, fn=op_crm_company_init
    ),
    "crm/namespaces/list_requested": Operation(
        payload_model=CrmOffsetPagePayload, fn=op_namespaces_list
    ),
    "crm/namespaces/create_requested": Operation(
        payload_model=NamespaceCreateRequest, fn=op_namespaces_create
    ),
    "crm/namespaces/update_requested": Operation(
        payload_model=CrmNamespaceUpdatePayload, fn=op_namespaces_update
    ),
    "crm/namespaces/editability_requested": Operation(
        payload_model=CrmNamespaceNamePayload, fn=op_namespaces_editability
    ),
    "crm/templates/list_requested": Operation(
        payload_model=CrmOffsetPagePayload, fn=op_templates_list
    ),
    "crm/templates/item_requested": Operation(
        payload_model=CrmTemplateIdPayload, fn=op_templates_item
    ),
    "crm/templates/create_requested": Operation(
        payload_model=NamespaceTemplateCreateRequest, fn=op_templates_create
    ),
    "crm/templates/update_requested": Operation(
        payload_model=CrmTemplateUpdatePayload, fn=op_templates_update
    ),
    "crm/templates/remove_requested": Operation(
        payload_model=CrmTemplateIdPayload, fn=op_templates_remove
    ),
    "crm/templates/schema_options_requested": Operation(
        payload_model=EmptyPayload, fn=op_templates_schema_options
    ),
    "crm/templates/type_upsert_requested": Operation(
        payload_model=CrmTemplateTypeUpsertPayload, fn=op_templates_type_upsert
    ),
    "crm/templates/type_remove_requested": Operation(
        payload_model=CrmTemplateTypeRemovePayload, fn=op_templates_type_remove
    ),
    "crm/entity_types/list_requested": Operation(
        payload_model=CrmEntityTypesListPayload, fn=op_entity_types_list
    ),
    "crm/entity_types/item_requested": Operation(
        payload_model=CrmEntityTypeKeyPayload, fn=op_entity_types_item
    ),
    "crm/entity_types/create_requested": Operation(
        payload_model=EntityTypeCreate, fn=op_entity_types_create
    ),
    "crm/entity_types/update_requested": Operation(
        payload_model=CrmEntityTypeUpdatePayload, fn=op_entity_types_update
    ),
    "crm/entity_types/public_fields_requested": Operation(
        payload_model=CrmEntityTypePublicFieldsPayload, fn=op_entity_types_public_fields
    ),
    "crm/grants/list_requested": Operation(
        payload_model=CrmGrantsListPayload, fn=op_grants_list
    ),
    "crm/grants/create_requested": Operation(
        payload_model=CrmGrantCreatePayload, fn=op_grants_create
    ),
    "crm/grants/item_requested": Operation(
        payload_model=CrmGrantIdPayload, fn=op_grants_item
    ),
    "crm/grants/remove_requested": Operation(
        payload_model=CrmGrantIdPayload, fn=op_grants_remove
    ),
    "crm/entities/create_requested": Operation(
        payload_model=EntityCreate, fn=op_entities_create
    ),
    "crm/entities/item_requested": Operation(
        payload_model=CrmEntityIdPayload, fn=op_entities_item
    ),
    "crm/entities/update_requested": Operation(
        payload_model=CrmEntityUpdatePayload, fn=op_entities_update
    ),
    "crm/entities/remove_requested": Operation(
        payload_model=CrmEntityIdPayload, fn=op_entities_remove
    ),
    "crm/entities/query_requested": Operation(
        payload_model=EntitySearchQueryRequest, fn=op_entities_query
    ),
    "crm/entities/mentions_search_requested": Operation(
        payload_model=SearchMentionsRequest, fn=op_entities_mentions_search
    ),
    "crm/entities/merge_requested": Operation(
        payload_model=EntityMergeRequest, fn=op_entities_merge
    ),
    "crm/entities/bulk_create_requested": Operation(
        payload_model=BulkCreateRequest, fn=op_entities_bulk_create
    ),
    "crm/entities/bulk_update_requested": Operation(
        payload_model=BulkUpdateRequest, fn=op_entities_bulk_update
    ),
    "crm/entities/bulk_delete_requested": Operation(
        payload_model=BulkDeleteRequest, fn=op_entities_bulk_delete
    ),
    "crm/entities/card_requested": Operation(
        payload_model=CrmEntityIdPayload, fn=op_entities_card
    ),
    "crm/entities/aggregate_requested": Operation(
        payload_model=CrmEntitiesAggregatePayload, fn=op_entities_aggregate
    ),
    "crm/entities/export_requested": Operation(
        payload_model=CrmEntitiesExportPayload, fn=op_entities_export
    ),
    "crm/entities/cards_bulk_requested": Operation(
        payload_model=BulkCardsRequest, fn=op_entities_cards_bulk
    ),
    "crm/notes/analysis_draft_save_requested": Operation(
        payload_model=CrmNoteAnalysisDraftSavePayload, fn=op_notes_analysis_draft_save
    ),
    "crm/notes/analysis_draft_discard_requested": Operation(
        payload_model=CrmNoteIdPayload, fn=op_notes_analysis_draft_discard
    ),
    "crm/notes/analysis_error_dismiss_requested": Operation(
        payload_model=CrmNoteIdPayload, fn=op_notes_analysis_error_dismiss
    ),
    "crm/notes/analysis_draft_repair_requested": Operation(
        payload_model=CrmNoteIdPayload, fn=op_notes_analysis_draft_repair
    ),
    "crm/notes/markdown_format_requested": Operation(
        payload_model=CrmNoteIdPayload, fn=op_notes_markdown_format
    ),
    "crm/notes/analyze_requested": Operation(
        payload_model=StartNoteAnalyzeRequest, fn=op_notes_analyze
    ),
    "crm/entities/person_self_requested": Operation(
        payload_model=EmptyPayload, fn=op_entities_person_self
    ),
    "crm/entities/timeline_bounds_requested": Operation(
        payload_model=CrmEntitiesTimelineBoundsPayload, fn=op_entities_timeline_bounds
    ),
    "crm/entities/overview_graph_requested": Operation(
        payload_model=CrmOverviewGraphPayload, fn=op_entities_overview_graph
    ),
    "crm/entities/influence_graph_requested": Operation(
        payload_model=CrmEntitiesInfluenceGraphPayload, fn=op_entities_influence_graph
    ),
    "crm/entities/related_requested": Operation(
        payload_model=CrmEntitiesRelatedPayload, fn=op_entities_related
    ),
    "crm/entities/relationships_requested": Operation(
        payload_model=CrmEntityIdPayload, fn=op_entities_relationships
    ),
    "crm/entities/exclusive_related_requested": Operation(
        payload_model=CrmEntityIdPayload, fn=op_entities_exclusive_related
    ),
    "crm/relationships/path_requested": Operation(
        payload_model=CrmRelationshipsPathPayload, fn=op_relationships_path
    ),
    "crm/relationships/list_requested": Operation(
        payload_model=CrmRelationshipsListPayload, fn=op_relationships_list
    ),
    "crm/relationships/item_requested": Operation(
        payload_model=CrmRelationshipIdPayload, fn=op_relationships_item
    ),
    "crm/relationships/create_requested": Operation(
        payload_model=RelationshipCreate, fn=op_relationships_create
    ),
    "crm/relationships/remove_requested": Operation(
        payload_model=CrmRelationshipIdPayload, fn=op_relationships_remove
    ),
    "crm/relationship_types/list_requested": Operation(
        payload_model=CrmOffsetPagePayload, fn=op_relationship_types_list
    ),
    "crm/relationship_types/create_requested": Operation(
        payload_model=RelationshipTypeCreate, fn=op_relationship_types_create
    ),
    "crm/suggests/list_requested": Operation(
        payload_model=CrmSuggestsListPayload, fn=op_suggests_list
    ),
    "crm/suggests/resolve_requested": Operation(
        payload_model=CrmSuggestKeyPayload, fn=op_suggests_resolve
    ),
    "crm/suggests/dismiss_requested": Operation(
        payload_model=CrmSuggestKeyPayload, fn=op_suggests_dismiss
    ),
    "crm/access_requests/list_requested": Operation(
        payload_model=CrmAccessRequestListPayload, fn=op_access_requests_list
    ),
    "crm/access_requests/create_requested": Operation(
        payload_model=AccessRequestCreate, fn=op_access_requests_create
    ),
    "crm/access_requests/item_requested": Operation(
        payload_model=CrmAccessRequestIdPayload, fn=op_access_requests_item
    ),
    "crm/access_requests/update_requested": Operation(
        payload_model=CrmAccessRequestUpdatePayload, fn=op_access_requests_update
    ),
    "crm/entities/daily_summary_requested": Operation(
        payload_model=DailySummaryRequest, fn=op_entities_daily_summary
    ),
    "crm/entities/period_summary_requested": Operation(
        payload_model=PeriodSummaryRequest, fn=op_entities_period_summary
    ),
    "crm/namespaces/lara_summary_requested": Operation(
        payload_model=CrmLaraSummaryPayload, fn=op_namespaces_lara_summary
    ),
    "crm/tasks/daily_summary_start_requested": Operation(
        payload_model=StartDailySummaryRequest, fn=op_tasks_daily_summary_start
    ),
    "crm/tasks/period_summary_start_requested": Operation(
        payload_model=StartPeriodSummaryRequest, fn=op_tasks_period_summary_start
    ),
    "crm/tasks/list_requested": Operation(
        payload_model=CrmTasksListPayload, fn=op_tasks_list
    ),
    "crm/tasks/item_requested": Operation(
        payload_model=CrmTaskIdPayload, fn=op_tasks_item
    ),
    "crm/tasks/created_entities_requested": Operation(
        payload_model=CrmTaskIdPayload, fn=op_tasks_created_entities
    ),
    "crm/tasks/knowledge_import_start_requested": Operation(
        payload_model=StartKnowledgeImportRequest, fn=op_tasks_knowledge_import_start
    ),
    "crm/tasks/review_complete_requested": Operation(
        payload_model=CrmTaskIdPayload, fn=op_tasks_review_complete
    ),
    "crm/tasks/cancel_requested": Operation(
        payload_model=CrmTaskIdPayload, fn=op_tasks_cancel
    ),
    "crm/tasks/rollback_requested": Operation(
        payload_model=CrmTaskIdPayload, fn=op_tasks_rollback
    ),
    "crm/tasks/retry_requested": Operation(
        payload_model=CrmTaskIdPayload, fn=op_tasks_retry
    ),
    "crm/activity_tasks/create_requested": Operation(
        payload_model=ActivityTaskCreateRequest, fn=op_activity_tasks_create
    ),
    "crm/activity_tasks/list_requested": Operation(
        payload_model=CrmActivityTasksListPayload, fn=op_activity_tasks_list
    ),
    "crm/attachments/list_requested": Operation(
        payload_model=CrmEntityIdPayload, fn=op_attachments_list
    ),
    "crm/attachments/attach_requested": Operation(
        payload_model=CrmAttachmentsAttachPayload, fn=op_attachments_attach
    ),
    "crm/attachments/remove_requested": Operation(
        payload_model=CrmAttachmentsRemovePayload, fn=op_attachments_remove
    ),
    "crm/namespace_integrations/list_requested": Operation(
        payload_model=CrmIntegrationNamespacePayload, fn=op_namespace_integrations_list
    ),
    "crm/namespace_integrations/authorize_requested": Operation(
        payload_model=CrmIntegrationAuthorizePayload,
        fn=op_namespace_integrations_authorize,
    ),
    "crm/namespace_integrations/auto_sync_requested": Operation(
        payload_model=CrmIntegrationAutoSyncPayload,
        fn=op_namespace_integrations_auto_sync,
    ),
    "crm/namespace_integrations/auto_note_ai_requested": Operation(
        payload_model=CrmIntegrationAutoNoteAiPayload,
        fn=op_namespace_integrations_auto_note_ai,
    ),
    "crm/namespace_integrations/sync_requested": Operation(
        payload_model=CrmIntegrationProviderPayload, fn=op_namespace_integrations_sync
    ),
    "crm/namespace_integrations/custom_fields_sync_requested": Operation(
        payload_model=CrmIntegrationProviderPayload,
        fn=op_namespace_integrations_custom_fields_sync,
    ),
}


def register_crm_ws_commands() -> None:
    register_service_operations(CRM_OPERATIONS, get_crm_container)
    logger.info("crm.ws.command.handlers", CRM_OPERATIONS_count=len(CRM_OPERATIONS))
