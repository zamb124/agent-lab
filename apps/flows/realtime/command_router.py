"""Регистрация WS command-handler'ов каталога Flows в `core.websocket`."""

from __future__ import annotations

from apps.flows.di import FlowsDi
from apps.flows.realtime.agent_skill_operations import (
    op_flows_agent_skills_create,
    op_flows_agent_skills_ensure_seed,
    op_flows_agent_skills_import,
    op_flows_agent_skills_item,
    op_flows_agent_skills_list,
    op_flows_agent_skills_remove,
    op_flows_agent_skills_update,
)
from apps.flows.realtime.browser_preview_operations import (
    BrowserPreviewClickPayload,
    BrowserPreviewKeyPayload,
    BrowserPreviewSessionPayload,
    BrowserPreviewTakeoverPayload,
    BrowserPreviewTaskPayload,
    BrowserPreviewTextPayload,
    op_flows_browser_preview_active_session,
    op_flows_browser_preview_click,
    op_flows_browser_preview_key,
    op_flows_browser_preview_status,
    op_flows_browser_preview_takeover,
    op_flows_browser_preview_takeover_release,
    op_flows_browser_preview_text,
)
from apps.flows.realtime.code_agent_operations import (
    op_flows_code_agent_copy_tree,
    op_flows_code_agent_delete,
    op_flows_code_agent_ensure_source,
    op_flows_code_agent_import_archive,
    op_flows_code_agent_import_git,
    op_flows_code_agent_logs,
    op_flows_code_agent_rebuild,
    op_flows_code_agent_status,
)
from apps.flows.realtime.code_operations import (
    op_flows_code_documentation,
    op_flows_code_editor_state,
    op_flows_code_execute,
    op_flows_code_flow_functions,
    op_flows_code_parse_signature,
    op_flows_code_source,
    op_flows_code_templates,
    op_flows_code_tool_source,
    op_flows_code_validate,
)
from apps.flows.realtime.company_operations import (
    CompanyInitPayload,
    op_flows_company_init,
)
from apps.flows.realtime.data_table_operations import op_flows_data_tables_create
from apps.flows.realtime.datasource_operations import (
    op_flows_datasources_connectors_list,
    op_flows_datasources_connectors_upsert,
    op_flows_datasources_create,
    op_flows_datasources_execute,
    op_flows_datasources_introspect,
    op_flows_datasources_item,
    op_flows_datasources_list,
    op_flows_datasources_query,
    op_flows_datasources_remove,
    op_flows_datasources_test,
    op_flows_datasources_update,
)
from apps.flows.realtime.durable_operations import (
    op_flows_durable_branches,
    op_flows_durable_fork,
    op_flows_durable_history,
    op_flows_durable_manual_patch,
    op_flows_durable_retry_from_failure,
    op_flows_durable_rewind,
    op_flows_durable_state_at,
    op_flows_sessions_state,
    op_flows_sessions_state_update,
)
from apps.flows.realtime.evaluation_operations import (
    op_flows_evaluation_annotation_create,
    op_flows_evaluation_annotation_delete,
    op_flows_evaluation_annotation_update,
    op_flows_evaluation_annotations_list,
    op_flows_evaluation_baseline_compare,
    op_flows_evaluation_baseline_item,
    op_flows_evaluation_baseline_set,
    op_flows_evaluation_baselines_list,
    op_flows_evaluation_case_create,
    op_flows_evaluation_case_delete,
    op_flows_evaluation_case_from_case_run,
    op_flows_evaluation_case_from_dialog,
    op_flows_evaluation_case_from_trace,
    op_flows_evaluation_case_import,
    op_flows_evaluation_case_item,
    op_flows_evaluation_case_run_trace,
    op_flows_evaluation_case_update,
    op_flows_evaluation_cases_list,
    op_flows_evaluation_compare_runs,
    op_flows_evaluation_evaluator_catalog,
    op_flows_evaluation_gate_policies_list,
    op_flows_evaluation_gate_policy_archive,
    op_flows_evaluation_gate_policy_create,
    op_flows_evaluation_gate_policy_item,
    op_flows_evaluation_gate_policy_run,
    op_flows_evaluation_gate_policy_update,
    op_flows_evaluation_gate_result,
    op_flows_evaluation_matrix_get,
    op_flows_evaluation_monitor_archive,
    op_flows_evaluation_monitor_create,
    op_flows_evaluation_monitor_cycles_run_active,
    op_flows_evaluation_monitor_item,
    op_flows_evaluation_monitor_observation_case_create,
    op_flows_evaluation_monitor_observations,
    op_flows_evaluation_monitor_run_cycle,
    op_flows_evaluation_monitor_sample,
    op_flows_evaluation_monitor_update,
    op_flows_evaluation_monitors_list,
    op_flows_evaluation_pairwise_judgment_create,
    op_flows_evaluation_pairwise_judgments_list,
    op_flows_evaluation_rubric_archive,
    op_flows_evaluation_rubric_create,
    op_flows_evaluation_rubric_item,
    op_flows_evaluation_rubric_update,
    op_flows_evaluation_rubric_version_create,
    op_flows_evaluation_rubric_versions_list,
    op_flows_evaluation_rubrics_list,
    op_flows_evaluation_run_cancel,
    op_flows_evaluation_run_cases,
    op_flows_evaluation_run_create,
    op_flows_evaluation_run_events,
    op_flows_evaluation_run_events_page,
    op_flows_evaluation_run_get,
    op_flows_evaluation_run_jobs_enqueue_pending,
    op_flows_evaluation_runs_list,
    op_flows_evaluation_suite_archive,
    op_flows_evaluation_suite_create,
    op_flows_evaluation_suite_item,
    op_flows_evaluation_suite_update,
    op_flows_evaluation_suites_list,
)
from apps.flows.realtime.flow_ui_operations import (
    op_flows_flow_ui_assist,
    op_flows_flow_ui_schema,
    op_flows_flow_ui_templates,
)
from apps.flows.realtime.flow_ui_share_operations import (
    op_flows_flow_ui_shares_create,
    op_flows_flow_ui_shares_list,
    op_flows_flow_ui_shares_remove,
)
from apps.flows.realtime.hitl_operations import (
    op_flows_hitl_conversation_get,
    op_flows_hitl_conversation_send,
)
from apps.flows.realtime.lara_operations import (
    LaraPendingActionApplyPayload,
    op_flows_lara_pending_actions_apply,
)
from apps.flows.realtime.llm_context_operations import op_flows_llm_context_resolve_parent
from apps.flows.realtime.mcp_operations import (
    op_flows_mcp_branding_list,
    op_flows_mcp_branding_remove,
    op_flows_mcp_branding_slug_suggest,
    op_flows_mcp_branding_upsert,
    op_flows_mcp_catalog_install,
    op_flows_mcp_catalog_list,
    op_flows_mcp_catalog_uninstall,
    op_flows_mcp_servers_create,
    op_flows_mcp_servers_item,
    op_flows_mcp_servers_list,
    op_flows_mcp_servers_remove,
    op_flows_mcp_servers_reset_catalog_defaults,
    op_flows_mcp_servers_sync,
    op_flows_mcp_servers_test,
    op_flows_mcp_servers_update,
)
from apps.flows.realtime.node_operations import (
    op_flows_nodes_catalog_create,
    op_flows_nodes_catalog_item,
    op_flows_nodes_catalog_list,
    op_flows_nodes_catalog_remove,
    op_flows_nodes_catalog_update,
)
from apps.flows.realtime.observability_operations import (
    op_flows_logs_by_request,
    op_flows_logs_by_session,
    op_flows_logs_by_span,
    op_flows_logs_by_trace,
    op_flows_logs_by_user,
    op_flows_traces_by_session,
    op_flows_traces_by_task,
    op_flows_traces_by_trace,
    op_flows_traces_handoff_chain,
    op_flows_traces_search,
)
from apps.flows.realtime.operations import (
    FlowDataflowInspectRequest,
    FlowsBranchIdPayload,
    FlowsFlowIdPayload,
    FlowsFlowVersionPayload,
    FlowsListPayload,
    op_flows_branch_create,
    op_flows_branch_remove,
    op_flows_branch_update,
    op_flows_create,
    op_flows_dataflow_inspect,
    op_flows_exception_absorb_allow_names,
    op_flows_execution_limits,
    op_flows_item,
    op_flows_list,
    op_flows_metadata_update,
    op_flows_node_types,
    op_flows_nodes_bulk_delete,
    op_flows_preview_share,
    op_flows_reload_from_bundle,
    op_flows_remove,
    op_flows_resource_types,
    op_flows_store_bundles,
    op_flows_update,
    op_flows_validate,
    op_flows_version_item,
    op_flows_version_rollback,
    op_flows_versions_list,
    op_flows_voice_session_query,
)
from apps.flows.realtime.prompt_operations import op_flows_prompts_render
from apps.flows.realtime.registry_operations import (
    op_flows_registry_models_list,
    op_flows_registry_providers_list,
)
from apps.flows.realtime.resource_operations import (
    op_flows_resources_create,
    op_flows_resources_item,
    op_flows_resources_list,
    op_flows_resources_remove,
    op_flows_resources_update,
)
from apps.flows.realtime.session_operations import (
    op_flows_sessions_list,
    op_flows_sessions_remove,
)
from apps.flows.realtime.tool_operations import (
    op_flows_tools_contract,
    op_flows_tools_create,
    op_flows_tools_item,
    op_flows_tools_list,
    op_flows_tools_list_all,
    op_flows_tools_preview,
    op_flows_tools_remove,
    op_flows_tools_tag_groups,
)
from apps.flows.realtime.tool_runtime_operations import (
    ToolRuntimeCallPayload,
    ToolRuntimeManifestPayload,
    op_flows_tool_runtime_call,
    op_flows_tool_runtime_manifest,
)
from apps.flows.realtime.trigger_operations import (
    op_flows_platform_events_catalog,
    op_flows_triggers_create,
    op_flows_triggers_item,
    op_flows_triggers_list,
    op_flows_triggers_remove,
    op_flows_triggers_reregister,
    op_flows_triggers_test,
    op_flows_triggers_update,
    op_flows_triggers_verify,
)
from apps.flows.src.flow_ui.templates import FlowUITemplatesPayload
from apps.flows.src.models import BranchCreateRequest, BranchUpdateRequest
from apps.flows.src.models.agent_skill import (
    AgentSkill,
    AgentSkillIdPayload,
    AgentSkillImportRequest,
    AgentSkillListPayload,
    AgentSkillUpdatePayload,
)
from apps.flows.src.models.code_api import (
    CodeDocumentationPayload,
    CodeEditorStatePayload,
    CodeFlowFunctionsPayload,
    CodeSourcePayload,
    CodeTemplatesPayload,
    CodeToolSourcePayload,
    ExecuteRequest,
    ParseSignatureRequest,
    ValidateRequest,
)
from apps.flows.src.models.durable_api import (
    DurableForkPayload,
    DurableHistoryPayload,
    DurableManualPatchPayload,
    DurableRetryPayload,
    DurableRewindPayload,
    DurableSessionIdPayload,
    DurableSessionStatePayload,
    DurableSessionStateUpdatePayload,
    DurableStateAtPayload,
)
from apps.flows.src.models.evaluation_lab import (
    EvaluationActiveMonitorCyclesRequest,
    EvaluationAnnotationCreateRequest,
    EvaluationAnnotationIdPayload,
    EvaluationAnnotationUpdateRequest,
    EvaluationBaselineComparePayload,
    EvaluationBaselineItemPayload,
    EvaluationBaselineSetRequest,
    EvaluationCaseCreateRequest,
    EvaluationCaseImportRequest,
    EvaluationCaseRunCaseCreateRequest,
    EvaluationCaseRunIdPayload,
    EvaluationCaseUpdateRequest,
    EvaluationCompareRunsPayload,
    EvaluationDialogCaseCreateRequest,
    EvaluationEventsPagePayload,
    EvaluationFlowIdPayload,
    EvaluationGatePolicyCreateRequest,
    EvaluationGatePolicyIdPayload,
    EvaluationGatePolicyRunRequest,
    EvaluationGatePolicyUpdateRequest,
    EvaluationMatrixPayload,
    EvaluationMonitorCreateRequest,
    EvaluationMonitorCycleRequest,
    EvaluationMonitorIdPayload,
    EvaluationMonitorObservationCaseCreateRequest,
    EvaluationMonitorObservationsPayload,
    EvaluationMonitorSampleRequest,
    EvaluationMonitorUpdateRequest,
    EvaluationPairwiseJudgeRequest,
    EvaluationPendingJobsPayload,
    EvaluationRubricCreateRequest,
    EvaluationRubricIdPayload,
    EvaluationRubricUpdateRequest,
    EvaluationRubricVersionCreateRequest,
    EvaluationRunCreateRequest,
    EvaluationRunIdPayload,
    EvaluationRunsListPayload,
    EvaluationSuiteCaseIdPayload,
    EvaluationSuiteCreateRequest,
    EvaluationSuiteIdPayload,
    EvaluationSuiteUpdateRequest,
    EvaluationTraceCaseCreateRequest,
)
from apps.flows.src.models.flow_api import (
    BulkDeleteNodesRequest,
    FlowCreateRequest,
    FlowMetadataRequest,
    FlowPreviewShareRequest,
    FlowValidateRequest,
    FlowVoiceSessionQueryRequest,
)
from apps.flows.src.models.flow_ui_assist import FlowUIAssistRequest
from apps.flows.src.models.hitl_conversation import (
    HitlConversationWorkItemPayload,
    OperatorMessageRequest,
)
from apps.flows.src.models.llm_context_api import LlmContextResolveParentRequest
from apps.flows.src.models.mcp import (
    MCPServerConfig,
    MCPServerIdPayload,
    MCPServerListPayload,
    MCPServerUpdatePayload,
)
from apps.flows.src.models.mcp_branding import (
    MCPServerBrandingIdPayload,
    MCPServerBrandingListPayload,
    MCPServerBrandingSlugSuggestPayload,
    MCPServerBrandingUpsertPayload,
)
from apps.flows.src.models.mcp_catalog import MCPCatalogIdPayload, MCPCatalogListPayload
from apps.flows.src.models.node_config import (
    NodeConfig,
    NodeIdPayload,
    NodeListPayload,
)
from apps.flows.src.models.observability_api import (
    ObservabilityLogsQueryPayload,
    ObservabilityTraceQueryPayload,
    ObservabilityTraceSearchPayload,
)
from apps.flows.src.models.prompt_api import RenderPromptRequest
from apps.flows.src.models.registry_contracts import RegistryCatalogPayload
from apps.flows.src.models.resource import (
    ResourceDefinition,
    ResourceIdPayload,
    ResourceListPayload,
    ResourceUpdatePayload,
)
from apps.flows.src.models.session_config import SessionIdPayload, SessionListPayload
from apps.flows.src.models.tool_reference import (
    ToolCreateRequest,
    ToolsListAllPayload,
    ToolsListPayload,
    ToolsTagGroupsPayload,
    ToolsToolIdPayload,
)
from apps.flows.src.models.trigger_config import (
    TriggerCreatePayload,
    TriggerFlowIdPayload,
    TriggerTestRequest,
    TriggerUpdatePayload,
    TriggerVerifyPayload,
)
from apps.flows.src.services.tool_preview import ToolPreviewRequest
from core.data_tables.models import DataTableCreateRequest
from core.datasources.models import (
    DatasourceConnectionCreate,
    DatasourceConnectionPatchPayload,
    DatasourceConnectorUpsert,
    DatasourceListPayload,
    DatasourceSchemaArgs,
    DatasourceSqlCallArgs,
)
from core.guest_runtime.models import (
    CodeAgentCopyTreeRequest,
    CodeAgentDeletePayload,
    CodeAgentImportArchiveRequest,
    CodeAgentImportGitRequest,
    CodeAgentLogsPayload,
    CodeAgentNodeRefPayload,
    CodeAgentRebuildRequest,
)
from core.integrations.operations import (
    INTEGRATIONS_CREDENTIALS_LIST_OPERATION,
    INTEGRATIONS_CREDENTIALS_REMOVE_OPERATION,
    INTEGRATIONS_WORKSPACE_COMPANY_DELETE_OPERATION,
    INTEGRATIONS_WORKSPACE_COMPANY_GET_OPERATION,
    INTEGRATIONS_WORKSPACE_COMPANY_PUT_OPERATION,
)
from core.logging import get_logger
from core.models.flow_ui_share import (
    FlowUIShareCreatePayload,
    FlowUIShareGrantIdPayload,
    FlowUIShareListPayload,
)
from core.models.voice_providers_catalog import VoiceProvidersCatalogPayload
from core.voice.operations import op_voice_providers_catalog
from core.websocket import EmptyPayload
from core.websocket.operation import Operation, RegisteredOperation

logger = get_logger(__name__)

FLOWS_OPERATIONS: dict[str, RegisteredOperation[FlowsDi]] = {
    "flows/flows/list_requested": Operation(payload_model=FlowsListPayload, fn=op_flows_list),
    "flows/flows/item_requested": Operation(payload_model=FlowsFlowIdPayload, fn=op_flows_item),
    "flows/flows/create_requested": Operation(payload_model=FlowCreateRequest, fn=op_flows_create),
    "flows/flows/update_requested": Operation(payload_model=FlowCreateRequest, fn=op_flows_update),
    "flows/flows/remove_requested": Operation(payload_model=FlowsFlowIdPayload, fn=op_flows_remove),
    "flows/flows/store_bundles_requested": Operation(
        payload_model=EmptyPayload, fn=op_flows_store_bundles
    ),
    "flows/flows/validate_requested": Operation(
        payload_model=FlowValidateRequest, fn=op_flows_validate
    ),
    "flows/flows/reload_from_bundle_requested": Operation(
        payload_model=FlowsFlowIdPayload, fn=op_flows_reload_from_bundle
    ),
    "flows/flows/versions_list_requested": Operation(
        payload_model=FlowsFlowIdPayload, fn=op_flows_versions_list
    ),
    "flows/flows/version_item_requested": Operation(
        payload_model=FlowsFlowVersionPayload, fn=op_flows_version_item
    ),
    "flows/flows/version_rollback_requested": Operation(
        payload_model=FlowsFlowVersionPayload, fn=op_flows_version_rollback
    ),
    "flows/flows/branch_create_requested": Operation(
        payload_model=BranchCreateRequest, fn=op_flows_branch_create
    ),
    "flows/flows/branch_update_requested": Operation(
        payload_model=BranchUpdateRequest, fn=op_flows_branch_update
    ),
    "flows/flows/branch_remove_requested": Operation(
        payload_model=FlowsBranchIdPayload, fn=op_flows_branch_remove
    ),
    "flows/flows/voice_session_query_requested": Operation(
        payload_model=FlowVoiceSessionQueryRequest, fn=op_flows_voice_session_query
    ),
    "flows/flows/preview_share_requested": Operation(
        payload_model=FlowPreviewShareRequest, fn=op_flows_preview_share
    ),
    "flows/flows/nodes_bulk_delete_requested": Operation(
        payload_model=BulkDeleteNodesRequest, fn=op_flows_nodes_bulk_delete
    ),
    "flows/flows/metadata_update_requested": Operation(
        payload_model=FlowMetadataRequest, fn=op_flows_metadata_update
    ),
    "flows/flows/dataflow_inspect_requested": Operation(
        payload_model=FlowDataflowInspectRequest, fn=op_flows_dataflow_inspect
    ),
    "flows/metadata/node_types_requested": Operation(
        payload_model=EmptyPayload, fn=op_flows_node_types
    ),
    "flows/metadata/resource_types_requested": Operation(
        payload_model=EmptyPayload, fn=op_flows_resource_types
    ),
    "flows/metadata/exception_absorb_allow_names_requested": Operation(
        payload_model=EmptyPayload, fn=op_flows_exception_absorb_allow_names
    ),
    "flows/metadata/execution_limits_requested": Operation(
        payload_model=EmptyPayload, fn=op_flows_execution_limits
    ),
    "flows/tools/list_requested": Operation(payload_model=ToolsListPayload, fn=op_flows_tools_list),
    "flows/tools/item_requested": Operation(
        payload_model=ToolsToolIdPayload, fn=op_flows_tools_item
    ),
    "flows/tools/create_requested": Operation(
        payload_model=ToolCreateRequest, fn=op_flows_tools_create
    ),
    "flows/tools/remove_requested": Operation(
        payload_model=ToolsToolIdPayload, fn=op_flows_tools_remove
    ),
    "flows/tools/list_all_requested": Operation(
        payload_model=ToolsListAllPayload, fn=op_flows_tools_list_all
    ),
    "flows/tools/tag_groups_requested": Operation(
        payload_model=ToolsTagGroupsPayload, fn=op_flows_tools_tag_groups
    ),
    "flows/tools/preview_requested": Operation(
        payload_model=ToolPreviewRequest, fn=op_flows_tools_preview
    ),
    "flows/tools/contract_requested": Operation(
        payload_model=ToolsToolIdPayload, fn=op_flows_tools_contract
    ),
    "flows/triggers/list_requested": Operation(
        payload_model=FlowsFlowIdPayload, fn=op_flows_triggers_list
    ),
    "flows/triggers/item_requested": Operation(
        payload_model=TriggerFlowIdPayload, fn=op_flows_triggers_item
    ),
    "flows/triggers/create_requested": Operation(
        payload_model=TriggerCreatePayload, fn=op_flows_triggers_create
    ),
    "flows/triggers/update_requested": Operation(
        payload_model=TriggerUpdatePayload, fn=op_flows_triggers_update
    ),
    "flows/triggers/remove_requested": Operation(
        payload_model=TriggerFlowIdPayload, fn=op_flows_triggers_remove
    ),
    "flows/triggers/verify_requested": Operation(
        payload_model=TriggerVerifyPayload, fn=op_flows_triggers_verify
    ),
    "flows/triggers/reregister_requested": Operation(
        payload_model=TriggerFlowIdPayload, fn=op_flows_triggers_reregister
    ),
    "flows/triggers/test_requested": Operation(
        payload_model=TriggerTestRequest, fn=op_flows_triggers_test
    ),
    "flows/platform_events/catalog_requested": Operation(
        payload_model=EmptyPayload, fn=op_flows_platform_events_catalog
    ),
    "flows/code/documentation_requested": Operation(
        payload_model=CodeDocumentationPayload, fn=op_flows_code_documentation
    ),
    "flows/code/templates_requested": Operation(
        payload_model=CodeTemplatesPayload, fn=op_flows_code_templates
    ),
    "flows/code/editor_state_requested": Operation(
        payload_model=CodeEditorStatePayload, fn=op_flows_code_editor_state
    ),
    "flows/code/source_requested": Operation(
        payload_model=CodeSourcePayload, fn=op_flows_code_source
    ),
    "flows/code/flow_functions_requested": Operation(
        payload_model=CodeFlowFunctionsPayload, fn=op_flows_code_flow_functions
    ),
    "flows/code/tool_source_requested": Operation(
        payload_model=CodeToolSourcePayload, fn=op_flows_code_tool_source
    ),
    "flows/code/parse_signature_requested": Operation(
        payload_model=ParseSignatureRequest, fn=op_flows_code_parse_signature
    ),
    "flows/code/validate_requested": Operation(
        payload_model=ValidateRequest, fn=op_flows_code_validate
    ),
    "flows/code/execute_requested": Operation(
        payload_model=ExecuteRequest, fn=op_flows_code_execute
    ),
    "flows/datasources/list_requested": Operation(
        payload_model=DatasourceListPayload, fn=op_flows_datasources_list
    ),
    "flows/datasources/item_requested": Operation(
        payload_model=DatasourceSchemaArgs, fn=op_flows_datasources_item
    ),
    "flows/datasources/create_requested": Operation(
        payload_model=DatasourceConnectionCreate, fn=op_flows_datasources_create
    ),
    "flows/datasources/update_requested": Operation(
        payload_model=DatasourceConnectionPatchPayload, fn=op_flows_datasources_update
    ),
    "flows/datasources/remove_requested": Operation(
        payload_model=DatasourceSchemaArgs, fn=op_flows_datasources_remove
    ),
    "flows/datasources/test_requested": Operation(
        payload_model=DatasourceSchemaArgs, fn=op_flows_datasources_test
    ),
    "flows/datasources/introspect_requested": Operation(
        payload_model=DatasourceSchemaArgs, fn=op_flows_datasources_introspect
    ),
    "flows/datasources/query_requested": Operation(
        payload_model=DatasourceSqlCallArgs, fn=op_flows_datasources_query
    ),
    "flows/datasources/execute_requested": Operation(
        payload_model=DatasourceSqlCallArgs, fn=op_flows_datasources_execute
    ),
    "flows/datasources/connectors_list_requested": Operation(
        payload_model=EmptyPayload, fn=op_flows_datasources_connectors_list
    ),
    "flows/datasources/connectors_upsert_requested": Operation(
        payload_model=DatasourceConnectorUpsert, fn=op_flows_datasources_connectors_upsert
    ),
    "flows/flow_ui/schema_requested": Operation(
        payload_model=EmptyPayload, fn=op_flows_flow_ui_schema
    ),
    "flows/flow_ui/templates_requested": Operation(
        payload_model=FlowUITemplatesPayload, fn=op_flows_flow_ui_templates
    ),
    "flows/flow_ui/assist_requested": Operation(
        payload_model=FlowUIAssistRequest, fn=op_flows_flow_ui_assist
    ),
    "flows/flow_ui_shares/list_requested": Operation(
        payload_model=FlowUIShareListPayload, fn=op_flows_flow_ui_shares_list
    ),
    "flows/flow_ui_shares/create_requested": Operation(
        payload_model=FlowUIShareCreatePayload, fn=op_flows_flow_ui_shares_create
    ),
    "flows/flow_ui_shares/remove_requested": Operation(
        payload_model=FlowUIShareGrantIdPayload, fn=op_flows_flow_ui_shares_remove
    ),
    "flows/data_tables/create_requested": Operation(
        payload_model=DataTableCreateRequest, fn=op_flows_data_tables_create
    ),
    "flows/llm_context/resolve_parent_requested": Operation(
        payload_model=LlmContextResolveParentRequest,
        fn=op_flows_llm_context_resolve_parent,
    ),
    "flows/prompts/render_requested": Operation(
        payload_model=RenderPromptRequest, fn=op_flows_prompts_render
    ),
    "flows/registry/providers_list_requested": Operation(
        payload_model=RegistryCatalogPayload, fn=op_flows_registry_providers_list
    ),
    "flows/registry/models_list_requested": Operation(
        payload_model=RegistryCatalogPayload, fn=op_flows_registry_models_list
    ),
    "flows/resources/list_requested": Operation(
        payload_model=ResourceListPayload, fn=op_flows_resources_list
    ),
    "flows/resources/item_requested": Operation(
        payload_model=ResourceIdPayload, fn=op_flows_resources_item
    ),
    "flows/resources/create_requested": Operation(
        payload_model=ResourceDefinition, fn=op_flows_resources_create
    ),
    "flows/resources/update_requested": Operation(
        payload_model=ResourceUpdatePayload, fn=op_flows_resources_update
    ),
    "flows/resources/remove_requested": Operation(
        payload_model=ResourceIdPayload, fn=op_flows_resources_remove
    ),
    "flows/sessions/list_requested": Operation(
        payload_model=SessionListPayload, fn=op_flows_sessions_list
    ),
    "flows/sessions/remove_requested": Operation(
        payload_model=SessionIdPayload, fn=op_flows_sessions_remove
    ),
    "flows/sessions/state_requested": Operation(
        payload_model=DurableSessionStatePayload, fn=op_flows_sessions_state
    ),
    "flows/sessions/state_update_requested": Operation(
        payload_model=DurableSessionStateUpdatePayload, fn=op_flows_sessions_state_update
    ),
    "flows/durable/history_requested": Operation(
        payload_model=DurableHistoryPayload, fn=op_flows_durable_history
    ),
    "flows/durable/branches_requested": Operation(
        payload_model=DurableSessionIdPayload, fn=op_flows_durable_branches
    ),
    "flows/durable/state_at_requested": Operation(
        payload_model=DurableStateAtPayload, fn=op_flows_durable_state_at
    ),
    "flows/durable/fork_requested": Operation(
        payload_model=DurableForkPayload, fn=op_flows_durable_fork
    ),
    "flows/durable/rewind_requested": Operation(
        payload_model=DurableRewindPayload, fn=op_flows_durable_rewind
    ),
    "flows/durable/manual_patch_requested": Operation(
        payload_model=DurableManualPatchPayload, fn=op_flows_durable_manual_patch
    ),
    "flows/durable/retry_from_failure_requested": Operation(
        payload_model=DurableRetryPayload, fn=op_flows_durable_retry_from_failure
    ),
    "flows/agent_skills/list_requested": Operation(
        payload_model=AgentSkillListPayload, fn=op_flows_agent_skills_list
    ),
    "flows/agent_skills/item_requested": Operation(
        payload_model=AgentSkillIdPayload, fn=op_flows_agent_skills_item
    ),
    "flows/agent_skills/create_requested": Operation(
        payload_model=AgentSkill, fn=op_flows_agent_skills_create
    ),
    "flows/agent_skills/update_requested": Operation(
        payload_model=AgentSkillUpdatePayload, fn=op_flows_agent_skills_update
    ),
    "flows/agent_skills/remove_requested": Operation(
        payload_model=AgentSkillIdPayload, fn=op_flows_agent_skills_remove
    ),
    "flows/agent_skills/import_requested": Operation(
        payload_model=AgentSkillImportRequest, fn=op_flows_agent_skills_import
    ),
    "flows/agent_skills/ensure_seed_requested": Operation(
        payload_model=EmptyPayload, fn=op_flows_agent_skills_ensure_seed
    ),
    "flows/tool_runtime/manifest_requested": Operation(
        payload_model=ToolRuntimeManifestPayload, fn=op_flows_tool_runtime_manifest
    ),
    "flows/tool_runtime/call_requested": Operation(
        payload_model=ToolRuntimeCallPayload, fn=op_flows_tool_runtime_call
    ),
    "flows/browser_preview/status_requested": Operation(
        payload_model=BrowserPreviewSessionPayload, fn=op_flows_browser_preview_status
    ),
    "flows/browser_preview/active_session_requested": Operation(
        payload_model=BrowserPreviewTaskPayload, fn=op_flows_browser_preview_active_session
    ),
    "flows/browser_preview/click_requested": Operation(
        payload_model=BrowserPreviewClickPayload, fn=op_flows_browser_preview_click
    ),
    "flows/browser_preview/key_requested": Operation(
        payload_model=BrowserPreviewKeyPayload, fn=op_flows_browser_preview_key
    ),
    "flows/browser_preview/text_requested": Operation(
        payload_model=BrowserPreviewTextPayload, fn=op_flows_browser_preview_text
    ),
    "flows/browser_preview/takeover_requested": Operation(
        payload_model=BrowserPreviewTakeoverPayload, fn=op_flows_browser_preview_takeover
    ),
    "flows/browser_preview/takeover_release_requested": Operation(
        payload_model=BrowserPreviewSessionPayload, fn=op_flows_browser_preview_takeover_release
    ),
    "flows/mcp_servers/list_requested": Operation(
        payload_model=MCPServerListPayload, fn=op_flows_mcp_servers_list
    ),
    "flows/mcp_servers/item_requested": Operation(
        payload_model=MCPServerIdPayload, fn=op_flows_mcp_servers_item
    ),
    "flows/mcp_servers/create_requested": Operation(
        payload_model=MCPServerConfig, fn=op_flows_mcp_servers_create
    ),
    "flows/mcp_servers/update_requested": Operation(
        payload_model=MCPServerUpdatePayload, fn=op_flows_mcp_servers_update
    ),
    "flows/mcp_servers/remove_requested": Operation(
        payload_model=MCPServerIdPayload, fn=op_flows_mcp_servers_remove
    ),
    "flows/mcp_servers/sync_requested": Operation(
        payload_model=MCPServerIdPayload, fn=op_flows_mcp_servers_sync
    ),
    "flows/mcp_servers/test_requested": Operation(
        payload_model=MCPServerIdPayload, fn=op_flows_mcp_servers_test
    ),
    "flows/mcp_servers/reset_catalog_defaults_requested": Operation(
        payload_model=MCPServerIdPayload, fn=op_flows_mcp_servers_reset_catalog_defaults
    ),
    "flows/mcp_branding/list_requested": Operation(
        payload_model=MCPServerBrandingListPayload, fn=op_flows_mcp_branding_list
    ),
    "flows/mcp_branding/slug_suggest_requested": Operation(
        payload_model=MCPServerBrandingSlugSuggestPayload,
        fn=op_flows_mcp_branding_slug_suggest,
    ),
    "flows/mcp_branding/upsert_requested": Operation(
        payload_model=MCPServerBrandingUpsertPayload, fn=op_flows_mcp_branding_upsert
    ),
    "flows/mcp_branding/remove_requested": Operation(
        payload_model=MCPServerBrandingIdPayload, fn=op_flows_mcp_branding_remove
    ),
    "flows/mcp_catalog/list_requested": Operation(
        payload_model=MCPCatalogListPayload, fn=op_flows_mcp_catalog_list
    ),
    "flows/mcp_catalog/install_requested": Operation(
        payload_model=MCPCatalogIdPayload, fn=op_flows_mcp_catalog_install
    ),
    "flows/mcp_catalog/uninstall_requested": Operation(
        payload_model=MCPCatalogIdPayload, fn=op_flows_mcp_catalog_uninstall
    ),
    "flows/nodes_catalog/list_requested": Operation(
        payload_model=NodeListPayload, fn=op_flows_nodes_catalog_list
    ),
    "flows/nodes_catalog/item_requested": Operation(
        payload_model=NodeIdPayload, fn=op_flows_nodes_catalog_item
    ),
    "flows/nodes_catalog/create_requested": Operation(
        payload_model=NodeConfig, fn=op_flows_nodes_catalog_create
    ),
    "flows/nodes_catalog/update_requested": Operation(
        payload_model=NodeConfig, fn=op_flows_nodes_catalog_update
    ),
    "flows/nodes_catalog/remove_requested": Operation(
        payload_model=NodeIdPayload, fn=op_flows_nodes_catalog_remove
    ),
    "flows/evaluation/evaluator_catalog_requested": Operation(
        payload_model=EmptyPayload, fn=op_flows_evaluation_evaluator_catalog
    ),
    "flows/evaluation/suites_list_requested": Operation(
        payload_model=EvaluationFlowIdPayload, fn=op_flows_evaluation_suites_list
    ),
    "flows/evaluation/suite_create_requested": Operation(
        payload_model=EvaluationSuiteCreateRequest, fn=op_flows_evaluation_suite_create
    ),
    "flows/evaluation/suite_item_requested": Operation(
        payload_model=EvaluationSuiteIdPayload, fn=op_flows_evaluation_suite_item
    ),
    "flows/evaluation/suite_update_requested": Operation(
        payload_model=EvaluationSuiteUpdateRequest, fn=op_flows_evaluation_suite_update
    ),
    "flows/evaluation/suite_archive_requested": Operation(
        payload_model=EvaluationSuiteIdPayload, fn=op_flows_evaluation_suite_archive
    ),
    "flows/evaluation/cases_list_requested": Operation(
        payload_model=EvaluationSuiteIdPayload, fn=op_flows_evaluation_cases_list
    ),
    "flows/evaluation/case_create_requested": Operation(
        payload_model=EvaluationCaseCreateRequest, fn=op_flows_evaluation_case_create
    ),
    "flows/evaluation/case_item_requested": Operation(
        payload_model=EvaluationSuiteCaseIdPayload, fn=op_flows_evaluation_case_item
    ),
    "flows/evaluation/case_update_requested": Operation(
        payload_model=EvaluationCaseUpdateRequest, fn=op_flows_evaluation_case_update
    ),
    "flows/evaluation/case_delete_requested": Operation(
        payload_model=EvaluationSuiteCaseIdPayload, fn=op_flows_evaluation_case_delete
    ),
    "flows/evaluation/case_import_requested": Operation(
        payload_model=EvaluationCaseImportRequest, fn=op_flows_evaluation_case_import
    ),
    "flows/evaluation/case_from_dialog_requested": Operation(
        payload_model=EvaluationDialogCaseCreateRequest,
        fn=op_flows_evaluation_case_from_dialog,
    ),
    "flows/evaluation/case_from_case_run_requested": Operation(
        payload_model=EvaluationCaseRunCaseCreateRequest,
        fn=op_flows_evaluation_case_from_case_run,
    ),
    "flows/evaluation/case_from_trace_requested": Operation(
        payload_model=EvaluationTraceCaseCreateRequest,
        fn=op_flows_evaluation_case_from_trace,
    ),
    "flows/evaluation/runs_list_requested": Operation(
        payload_model=EvaluationRunsListPayload, fn=op_flows_evaluation_runs_list
    ),
    "flows/evaluation/run_create_requested": Operation(
        payload_model=EvaluationRunCreateRequest, fn=op_flows_evaluation_run_create
    ),
    "flows/evaluation/run_get_requested": Operation(
        payload_model=EvaluationRunIdPayload, fn=op_flows_evaluation_run_get
    ),
    "flows/evaluation/run_cancel_requested": Operation(
        payload_model=EvaluationRunIdPayload, fn=op_flows_evaluation_run_cancel
    ),
    "flows/evaluation/run_cases_requested": Operation(
        payload_model=EvaluationRunIdPayload, fn=op_flows_evaluation_run_cases
    ),
    "flows/evaluation/run_events_requested": Operation(
        payload_model=EvaluationRunIdPayload, fn=op_flows_evaluation_run_events
    ),
    "flows/evaluation/run_events_page_requested": Operation(
        payload_model=EvaluationEventsPagePayload, fn=op_flows_evaluation_run_events_page
    ),
    "flows/evaluation/run_jobs_enqueue_pending_requested": Operation(
        payload_model=EvaluationPendingJobsPayload,
        fn=op_flows_evaluation_run_jobs_enqueue_pending,
    ),
    "flows/evaluation/matrix_get_requested": Operation(
        payload_model=EvaluationMatrixPayload, fn=op_flows_evaluation_matrix_get
    ),
    "flows/evaluation/compare_runs_requested": Operation(
        payload_model=EvaluationCompareRunsPayload, fn=op_flows_evaluation_compare_runs
    ),
    "flows/evaluation/case_run_trace_requested": Operation(
        payload_model=EvaluationCaseRunIdPayload, fn=op_flows_evaluation_case_run_trace
    ),
    "flows/evaluation/annotations_list_requested": Operation(
        payload_model=EvaluationRunIdPayload, fn=op_flows_evaluation_annotations_list
    ),
    "flows/evaluation/annotation_create_requested": Operation(
        payload_model=EvaluationAnnotationCreateRequest,
        fn=op_flows_evaluation_annotation_create,
    ),
    "flows/evaluation/annotation_update_requested": Operation(
        payload_model=EvaluationAnnotationUpdateRequest,
        fn=op_flows_evaluation_annotation_update,
    ),
    "flows/evaluation/annotation_delete_requested": Operation(
        payload_model=EvaluationAnnotationIdPayload,
        fn=op_flows_evaluation_annotation_delete,
    ),
    "flows/evaluation/baselines_list_requested": Operation(
        payload_model=EvaluationSuiteIdPayload, fn=op_flows_evaluation_baselines_list
    ),
    "flows/evaluation/baseline_set_requested": Operation(
        payload_model=EvaluationBaselineSetRequest, fn=op_flows_evaluation_baseline_set
    ),
    "flows/evaluation/baseline_item_requested": Operation(
        payload_model=EvaluationBaselineItemPayload, fn=op_flows_evaluation_baseline_item
    ),
    "flows/evaluation/baseline_compare_requested": Operation(
        payload_model=EvaluationBaselineComparePayload,
        fn=op_flows_evaluation_baseline_compare,
    ),
    "flows/evaluation/gate_policies_list_requested": Operation(
        payload_model=EvaluationSuiteIdPayload, fn=op_flows_evaluation_gate_policies_list
    ),
    "flows/evaluation/gate_policy_create_requested": Operation(
        payload_model=EvaluationGatePolicyCreateRequest,
        fn=op_flows_evaluation_gate_policy_create,
    ),
    "flows/evaluation/gate_policy_item_requested": Operation(
        payload_model=EvaluationGatePolicyIdPayload,
        fn=op_flows_evaluation_gate_policy_item,
    ),
    "flows/evaluation/gate_policy_update_requested": Operation(
        payload_model=EvaluationGatePolicyUpdateRequest,
        fn=op_flows_evaluation_gate_policy_update,
    ),
    "flows/evaluation/gate_policy_archive_requested": Operation(
        payload_model=EvaluationGatePolicyIdPayload,
        fn=op_flows_evaluation_gate_policy_archive,
    ),
    "flows/evaluation/gate_policy_run_requested": Operation(
        payload_model=EvaluationGatePolicyRunRequest,
        fn=op_flows_evaluation_gate_policy_run,
    ),
    "flows/evaluation/gate_result_requested": Operation(
        payload_model=EvaluationRunIdPayload, fn=op_flows_evaluation_gate_result
    ),
    "flows/evaluation/monitors_list_requested": Operation(
        payload_model=EvaluationSuiteIdPayload, fn=op_flows_evaluation_monitors_list
    ),
    "flows/evaluation/monitor_create_requested": Operation(
        payload_model=EvaluationMonitorCreateRequest, fn=op_flows_evaluation_monitor_create
    ),
    "flows/evaluation/monitor_item_requested": Operation(
        payload_model=EvaluationMonitorIdPayload, fn=op_flows_evaluation_monitor_item
    ),
    "flows/evaluation/monitor_update_requested": Operation(
        payload_model=EvaluationMonitorUpdateRequest, fn=op_flows_evaluation_monitor_update
    ),
    "flows/evaluation/monitor_archive_requested": Operation(
        payload_model=EvaluationMonitorIdPayload, fn=op_flows_evaluation_monitor_archive
    ),
    "flows/evaluation/monitor_sample_requested": Operation(
        payload_model=EvaluationMonitorSampleRequest, fn=op_flows_evaluation_monitor_sample
    ),
    "flows/evaluation/monitor_run_cycle_requested": Operation(
        payload_model=EvaluationMonitorCycleRequest,
        fn=op_flows_evaluation_monitor_run_cycle,
    ),
    "flows/evaluation/monitor_cycles_run_active_requested": Operation(
        payload_model=EvaluationActiveMonitorCyclesRequest,
        fn=op_flows_evaluation_monitor_cycles_run_active,
    ),
    "flows/evaluation/monitor_observations_requested": Operation(
        payload_model=EvaluationMonitorObservationsPayload,
        fn=op_flows_evaluation_monitor_observations,
    ),
    "flows/evaluation/monitor_observation_case_create_requested": Operation(
        payload_model=EvaluationMonitorObservationCaseCreateRequest,
        fn=op_flows_evaluation_monitor_observation_case_create,
    ),
    "flows/evaluation/pairwise_judgment_create_requested": Operation(
        payload_model=EvaluationPairwiseJudgeRequest,
        fn=op_flows_evaluation_pairwise_judgment_create,
    ),
    "flows/evaluation/pairwise_judgments_list_requested": Operation(
        payload_model=EvaluationCaseRunIdPayload,
        fn=op_flows_evaluation_pairwise_judgments_list,
    ),
    "flows/evaluation/rubrics_list_requested": Operation(
        payload_model=EvaluationFlowIdPayload, fn=op_flows_evaluation_rubrics_list
    ),
    "flows/evaluation/rubric_create_requested": Operation(
        payload_model=EvaluationRubricCreateRequest, fn=op_flows_evaluation_rubric_create
    ),
    "flows/evaluation/rubric_item_requested": Operation(
        payload_model=EvaluationRubricIdPayload, fn=op_flows_evaluation_rubric_item
    ),
    "flows/evaluation/rubric_update_requested": Operation(
        payload_model=EvaluationRubricUpdateRequest, fn=op_flows_evaluation_rubric_update
    ),
    "flows/evaluation/rubric_archive_requested": Operation(
        payload_model=EvaluationRubricIdPayload, fn=op_flows_evaluation_rubric_archive
    ),
    "flows/evaluation/rubric_versions_list_requested": Operation(
        payload_model=EvaluationRubricIdPayload,
        fn=op_flows_evaluation_rubric_versions_list,
    ),
    "flows/evaluation/rubric_version_create_requested": Operation(
        payload_model=EvaluationRubricVersionCreateRequest,
        fn=op_flows_evaluation_rubric_version_create,
    ),
    "flows/code_agent/ensure_source_requested": Operation(
        payload_model=CodeAgentNodeRefPayload, fn=op_flows_code_agent_ensure_source
    ),
    "flows/code_agent/import_git_requested": Operation(
        payload_model=CodeAgentImportGitRequest, fn=op_flows_code_agent_import_git
    ),
    "flows/code_agent/import_archive_requested": Operation(
        payload_model=CodeAgentImportArchiveRequest,
        fn=op_flows_code_agent_import_archive,
    ),
    "flows/code_agent/copy_tree_requested": Operation(
        payload_model=CodeAgentCopyTreeRequest, fn=op_flows_code_agent_copy_tree
    ),
    "flows/code_agent/rebuild_requested": Operation(
        payload_model=CodeAgentRebuildRequest, fn=op_flows_code_agent_rebuild
    ),
    "flows/code_agent/status_requested": Operation(
        payload_model=CodeAgentNodeRefPayload, fn=op_flows_code_agent_status
    ),
    "flows/code_agent/logs_requested": Operation(
        payload_model=CodeAgentLogsPayload, fn=op_flows_code_agent_logs
    ),
    "flows/code_agent/delete_requested": Operation(
        payload_model=CodeAgentDeletePayload, fn=op_flows_code_agent_delete
    ),
    "flows/logs/by_trace_requested": Operation(
        payload_model=ObservabilityLogsQueryPayload, fn=op_flows_logs_by_trace
    ),
    "flows/logs/by_session_requested": Operation(
        payload_model=ObservabilityLogsQueryPayload, fn=op_flows_logs_by_session
    ),
    "flows/logs/by_request_requested": Operation(
        payload_model=ObservabilityLogsQueryPayload, fn=op_flows_logs_by_request
    ),
    "flows/logs/by_span_requested": Operation(
        payload_model=ObservabilityLogsQueryPayload, fn=op_flows_logs_by_span
    ),
    "flows/logs/by_user_requested": Operation(
        payload_model=ObservabilityLogsQueryPayload, fn=op_flows_logs_by_user
    ),
    "flows/traces/search_requested": Operation(
        payload_model=ObservabilityTraceSearchPayload, fn=op_flows_traces_search
    ),
    "flows/traces/by_session_requested": Operation(
        payload_model=ObservabilityTraceQueryPayload, fn=op_flows_traces_by_session
    ),
    "flows/traces/by_task_requested": Operation(
        payload_model=ObservabilityTraceQueryPayload, fn=op_flows_traces_by_task
    ),
    "flows/traces/by_trace_requested": Operation(
        payload_model=ObservabilityTraceQueryPayload, fn=op_flows_traces_by_trace
    ),
    "flows/traces/handoff_chain_requested": Operation(
        payload_model=ObservabilityTraceQueryPayload, fn=op_flows_traces_handoff_chain
    ),
    "flows/voice_providers/catalog_requested": Operation(
        payload_model=VoiceProvidersCatalogPayload,
        fn=op_voice_providers_catalog,
    ),
    "flows/hitl/conversation_get_requested": Operation(
        payload_model=HitlConversationWorkItemPayload,
        fn=op_flows_hitl_conversation_get,
    ),
    "flows/hitl/conversation_send_requested": Operation(
        payload_model=OperatorMessageRequest,
        fn=op_flows_hitl_conversation_send,
    ),
    "flows/lara/pending_actions_apply_requested": Operation(
        payload_model=LaraPendingActionApplyPayload,
        fn=op_flows_lara_pending_actions_apply,
    ),
    "flows/company/init_requested": Operation(
        payload_model=CompanyInitPayload,
        fn=op_flows_company_init,
    ),
    "flows/integrations/credentials_list_requested": INTEGRATIONS_CREDENTIALS_LIST_OPERATION,
    "flows/integrations/credentials_remove_requested": INTEGRATIONS_CREDENTIALS_REMOVE_OPERATION,
    "flows/integrations/workspace_company_get_requested": INTEGRATIONS_WORKSPACE_COMPANY_GET_OPERATION,
    "flows/integrations/workspace_company_put_requested": INTEGRATIONS_WORKSPACE_COMPANY_PUT_OPERATION,
    "flows/integrations/workspace_company_delete_requested": INTEGRATIONS_WORKSPACE_COMPANY_DELETE_OPERATION,
}

