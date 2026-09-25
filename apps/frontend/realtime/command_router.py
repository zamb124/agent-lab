"""Каталог команд Frontend (консоль компании): `frontend/<entity>/<verb>_requested` → `op_*`."""

from __future__ import annotations

from apps.frontend.di import FrontendDi
from apps.frontend.models import (
    ApiKeyCreate,
    ChangePlanRequest,
    CompanySettingsUpdate,
    CustomProviderCreate,
    PlatformBillingBalanceGrantRequest,
)
from apps.frontend.realtime.agent_operations import (
    AgentAuditListPayload,
    AgentDeviceIdPayload,
    AgentDevicePolicyUpdatePayload,
    AgentDevicesListPayload,
    op_agent_audit_list,
    op_agent_devices_list,
    op_agent_devices_policy_update,
    op_agent_devices_revoke,
    op_agent_pairing_create,
)
from apps.frontend.realtime.ai_providers_operations import (
    AIProvidersCapabilityIdPayload,
    AIProvidersCapabilityPayload,
    AIProvidersSnapshotPayload,
    CustomProviderIdPayload,
    CustomProviderUpdatePayload,
    op_ai_providers_capability_remove,
    op_ai_providers_capability_update,
    op_ai_providers_custom_create,
    op_ai_providers_custom_remove,
    op_ai_providers_custom_update,
    op_ai_providers_llm_context_remove,
    op_ai_providers_llm_context_update,
    op_ai_providers_resolved,
    op_ai_providers_snapshot,
)
from apps.frontend.realtime.authz_explorer_operations import (
    AuthzExplorerByObjectPayload,
    AuthzExplorerByUserPayload,
    AuthzExplorerObjectsPayload,
    AuthzExplorerWhyPayload,
    op_authz_explorer_by_object,
    op_authz_explorer_by_user,
    op_authz_explorer_objects,
    op_authz_explorer_revoke,
    op_authz_explorer_why,
)
from apps.frontend.realtime.billing_operations import (
    BillingTopupPayload,
    op_billing_payment_history,
    op_billing_plan_change,
    op_billing_subscription,
    op_billing_topup,
    op_billing_usage,
)
from apps.frontend.realtime.companies_operations import (
    CompanyCreatePayload,
    CompanySlugCheckPayload,
    SystemAccessGrantPayload,
    SystemAccessRevokePayload,
    op_companies_create,
    op_companies_slug_check,
    op_companies_system_access_grant,
    op_companies_system_access_revoke,
)
from apps.frontend.realtime.company_operations import (
    ApiKeyIdPayload,
    ApiKeyRenamePayload,
    InviteGeneratePayload,
    OffsetPayload,
    TeamMemberIdPayload,
    TeamMemberRolesUpdatePayload,
    op_api_keys_create,
    op_api_keys_list,
    op_api_keys_rename,
    op_api_keys_revoke,
    op_company_settings_get,
    op_company_settings_update,
    op_invites_generate,
    op_team_member_remove,
    op_team_member_roles_update,
)
from apps.frontend.realtime.company_storage_operations import (
    CompanyStorageCreatePayload,
    CompanyStorageIdPayload,
    CompanyStorageMigrationIdPayload,
    CompanyStorageMigrationStartPayload,
    CompanyStorageRotatePayload,
    CompanyStorageRoutePayload,
    StorageConnectionPayload,
    op_company_storage_migrations_get,
    op_company_storage_migrations_start,
    op_company_storage_routes_set,
    op_company_storages_create,
    op_company_storages_delete,
    op_company_storages_list,
    op_company_storages_probe,
    op_company_storages_rotate,
)
from apps.frontend.realtime.embed_operations import (
    CreateEmbedConfigRequest,
    EmbedCodePayload,
    EmbedConfigsListPayload,
    EmbedConfigUpdatePayload,
    EmbedIdPayload,
    op_embed_configs_code,
    op_embed_configs_create,
    op_embed_configs_item,
    op_embed_configs_list,
    op_embed_configs_remove,
    op_embed_configs_update,
)
from apps.frontend.realtime.leads_operations import LeadRequestsListPayload, op_lead_requests_list
from apps.frontend.realtime.llm_model_scores_operations import (
    LLMModelScoreDeletePayload,
    LLMModelScoreUpsertRequest,
    op_llm_model_scores_delete,
    op_llm_model_scores_list,
    op_llm_model_scores_probe_providers,
    op_llm_model_scores_refresh_cache,
    op_llm_model_scores_upsert,
)
from apps.frontend.realtime.namespace_operations import (
    ConsoleNamespaceCreatePayload,
    ConsoleNamespacesListPayload,
    op_namespaces_console_create,
    op_namespaces_console_list,
    op_namespaces_personal,
)
from apps.frontend.realtime.operations import op_dashboard_stats
from apps.frontend.realtime.platform_billing_operations import (
    PlatformBillingCompanyIdPayload,
    PlatformBillingCompanyPricesPutPayload,
    PlatformBillingCompanyQueryPayload,
    PlatformBillingFacetPayload,
    PlatformBillingOverviewPayload,
    PlatformBillingPricesPutPayload,
    PlatformBillingSettlementRulesPutPayload,
    PlatformBillingUsageReportPayload,
    op_platform_billing_balance_grant,
    op_platform_billing_companies_overview,
    op_platform_billing_company_prices,
    op_platform_billing_company_prices_update,
    op_platform_billing_company_resolve,
    op_platform_billing_default_settlement_rules,
    op_platform_billing_facet_companies,
    op_platform_billing_facet_resource_names,
    op_platform_billing_facet_usage_types,
    op_platform_billing_prices,
    op_platform_billing_prices_update,
    op_platform_billing_settlement_rules,
    op_platform_billing_settlement_rules_update,
    op_platform_billing_usage_report,
)
from apps.frontend.realtime.platform_tracing_operations import (
    TracingFacetPayload,
    TracingSpansPayload,
    TracingTraceIdPayload,
    op_platform_tracing_facet_companies,
    op_platform_tracing_facet_event_types,
    op_platform_tracing_facet_namespaces,
    op_platform_tracing_facet_operations,
    op_platform_tracing_facet_services,
    op_platform_tracing_facet_users,
    op_platform_tracing_spans,
    op_platform_tracing_trace_tree,
)
from core.authz.explorer import AuthzExplorerRevokeRequest
from core.identity.team_operations import TEAM_MEMBERS_LIST_OPERATION
from core.llm_context import LLMContextPatch
from core.websocket import EmptyPayload, Operation, RegisteredOperation

FRONTEND_OPERATIONS: dict[str, RegisteredOperation[FrontendDi]] = {
    "frontend/dashboard/stats_requested": Operation(payload_model=EmptyPayload, fn=op_dashboard_stats),
    "frontend/company_settings/get_requested": Operation(
        payload_model=EmptyPayload, fn=op_company_settings_get
    ),
    "frontend/company_settings/update_requested": Operation(
        payload_model=CompanySettingsUpdate, fn=op_company_settings_update
    ),
    "frontend/company_storages/list_requested": Operation(
        payload_model=EmptyPayload, fn=op_company_storages_list
    ),
    "frontend/company_storages/create_requested": Operation(
        payload_model=CompanyStorageCreatePayload, fn=op_company_storages_create
    ),
    "frontend/company_storages/probe_requested": Operation(
        payload_model=StorageConnectionPayload, fn=op_company_storages_probe
    ),
    "frontend/company_storages/rotate_credentials_requested": Operation(
        payload_model=CompanyStorageRotatePayload, fn=op_company_storages_rotate
    ),
    "frontend/company_storages/delete_requested": Operation(
        payload_model=CompanyStorageIdPayload, fn=op_company_storages_delete
    ),
    "frontend/company_storage_routes/set_requested": Operation(
        payload_model=CompanyStorageRoutePayload, fn=op_company_storage_routes_set
    ),
    "frontend/company_storage_migrations/start_requested": Operation(
        payload_model=CompanyStorageMigrationStartPayload, fn=op_company_storage_migrations_start
    ),
    "frontend/company_storage_migrations/get_requested": Operation(
        payload_model=CompanyStorageMigrationIdPayload, fn=op_company_storage_migrations_get
    ),
    "frontend/team/list_requested": TEAM_MEMBERS_LIST_OPERATION,
    "frontend/team/update_requested": Operation(
        payload_model=TeamMemberRolesUpdatePayload, fn=op_team_member_roles_update
    ),
    "frontend/team/remove_requested": Operation(payload_model=TeamMemberIdPayload, fn=op_team_member_remove),
    "frontend/invites/generate_requested": Operation(payload_model=InviteGeneratePayload, fn=op_invites_generate),
    "frontend/api_keys/list_requested": Operation(payload_model=OffsetPayload, fn=op_api_keys_list),
    "frontend/api_keys/create_requested": Operation(payload_model=ApiKeyCreate, fn=op_api_keys_create),
    "frontend/api_keys/update_requested": Operation(payload_model=ApiKeyRenamePayload, fn=op_api_keys_rename),
    "frontend/api_keys/remove_requested": Operation(payload_model=ApiKeyIdPayload, fn=op_api_keys_revoke),
    "frontend/namespaces/list_requested": Operation(
        payload_model=ConsoleNamespacesListPayload, fn=op_namespaces_console_list
    ),
    "frontend/namespaces/create_requested": Operation(
        payload_model=ConsoleNamespaceCreatePayload, fn=op_namespaces_console_create
    ),
    "frontend/namespaces/personal_requested": Operation(payload_model=EmptyPayload, fn=op_namespaces_personal),
    "frontend/companies/slug_check_requested": Operation(
        payload_model=CompanySlugCheckPayload, fn=op_companies_slug_check
    ),
    "frontend/companies/create_requested": Operation(payload_model=CompanyCreatePayload, fn=op_companies_create),
    "frontend/companies/system_access_grant_requested": Operation(
        payload_model=SystemAccessGrantPayload, fn=op_companies_system_access_grant
    ),
    "frontend/companies/system_access_revoke_requested": Operation(
        payload_model=SystemAccessRevokePayload, fn=op_companies_system_access_revoke
    ),
    "frontend/authz_explorer/by_user_requested": Operation(
        payload_model=AuthzExplorerByUserPayload, fn=op_authz_explorer_by_user
    ),
    "frontend/authz_explorer/by_object_requested": Operation(
        payload_model=AuthzExplorerByObjectPayload, fn=op_authz_explorer_by_object
    ),
    "frontend/authz_explorer/why_requested": Operation(payload_model=AuthzExplorerWhyPayload, fn=op_authz_explorer_why),
    "frontend/authz_explorer/objects_requested": Operation(
        payload_model=AuthzExplorerObjectsPayload, fn=op_authz_explorer_objects
    ),
    "frontend/authz_explorer/revoke_requested": Operation(
        payload_model=AuthzExplorerRevokeRequest, fn=op_authz_explorer_revoke
    ),
    "frontend/billing/subscription_requested": Operation(
        payload_model=EmptyPayload, fn=op_billing_subscription
    ),
    "frontend/billing/usage_requested": Operation(payload_model=EmptyPayload, fn=op_billing_usage),
    "frontend/billing/plan_change_requested": Operation(payload_model=ChangePlanRequest, fn=op_billing_plan_change),
    "frontend/billing/topup_requested": Operation(payload_model=BillingTopupPayload, fn=op_billing_topup),
    "frontend/billing/payment_history_requested": Operation(
        payload_model=EmptyPayload, fn=op_billing_payment_history
    ),
    "frontend/platform_billing/companies_overview_requested": Operation(
        payload_model=PlatformBillingOverviewPayload, fn=op_platform_billing_companies_overview
    ),
    "frontend/platform_billing/balance_grant_requested": Operation(
        payload_model=PlatformBillingBalanceGrantRequest, fn=op_platform_billing_balance_grant
    ),
    "frontend/platform_billing/company_resolve_requested": Operation(
        payload_model=PlatformBillingCompanyQueryPayload, fn=op_platform_billing_company_resolve
    ),
    "frontend/platform_billing/facet_companies_requested": Operation(
        payload_model=PlatformBillingFacetPayload, fn=op_platform_billing_facet_companies
    ),
    "frontend/platform_billing/prices_requested": Operation(
        payload_model=EmptyPayload, fn=op_platform_billing_prices
    ),
    "frontend/platform_billing/prices_update_requested": Operation(
        payload_model=PlatformBillingPricesPutPayload, fn=op_platform_billing_prices_update
    ),
    "frontend/platform_billing/default_settlement_rules_requested": Operation(
        payload_model=EmptyPayload, fn=op_platform_billing_default_settlement_rules
    ),
    "frontend/platform_billing/settlement_rules_requested": Operation(
        payload_model=PlatformBillingCompanyIdPayload, fn=op_platform_billing_settlement_rules
    ),
    "frontend/platform_billing/settlement_rules_update_requested": Operation(
        payload_model=PlatformBillingSettlementRulesPutPayload, fn=op_platform_billing_settlement_rules_update
    ),
    "frontend/platform_billing/company_prices_requested": Operation(
        payload_model=PlatformBillingCompanyIdPayload, fn=op_platform_billing_company_prices
    ),
    "frontend/platform_billing/company_prices_update_requested": Operation(
        payload_model=PlatformBillingCompanyPricesPutPayload, fn=op_platform_billing_company_prices_update
    ),
    "frontend/platform_billing/facet_usage_types_requested": Operation(
        payload_model=PlatformBillingFacetPayload, fn=op_platform_billing_facet_usage_types
    ),
    "frontend/platform_billing/facet_resource_names_requested": Operation(
        payload_model=PlatformBillingFacetPayload, fn=op_platform_billing_facet_resource_names
    ),
    "frontend/platform_billing/usage_report_requested": Operation(
        payload_model=PlatformBillingUsageReportPayload, fn=op_platform_billing_usage_report
    ),
    "frontend/platform_tracing/facet_companies_requested": Operation(
        payload_model=TracingFacetPayload, fn=op_platform_tracing_facet_companies
    ),
    "frontend/platform_tracing/facet_users_requested": Operation(
        payload_model=TracingFacetPayload, fn=op_platform_tracing_facet_users
    ),
    "frontend/platform_tracing/facet_services_requested": Operation(
        payload_model=TracingFacetPayload, fn=op_platform_tracing_facet_services
    ),
    "frontend/platform_tracing/facet_event_types_requested": Operation(
        payload_model=TracingFacetPayload, fn=op_platform_tracing_facet_event_types
    ),
    "frontend/platform_tracing/facet_namespaces_requested": Operation(
        payload_model=TracingFacetPayload, fn=op_platform_tracing_facet_namespaces
    ),
    "frontend/platform_tracing/facet_operations_requested": Operation(
        payload_model=TracingFacetPayload, fn=op_platform_tracing_facet_operations
    ),
    "frontend/platform_tracing/spans_requested": Operation(payload_model=TracingSpansPayload, fn=op_platform_tracing_spans),
    "frontend/platform_tracing/trace_tree_requested": Operation(
        payload_model=TracingTraceIdPayload, fn=op_platform_tracing_trace_tree
    ),
    "frontend/llm_model_scores/list_requested": Operation(
        payload_model=EmptyPayload, fn=op_llm_model_scores_list
    ),
    "frontend/llm_model_scores/upsert_requested": Operation(
        payload_model=LLMModelScoreUpsertRequest, fn=op_llm_model_scores_upsert
    ),
    "frontend/llm_model_scores/delete_requested": Operation(
        payload_model=LLMModelScoreDeletePayload, fn=op_llm_model_scores_delete
    ),
    "frontend/llm_model_scores/refresh_cache_requested": Operation(
        payload_model=EmptyPayload, fn=op_llm_model_scores_refresh_cache
    ),
    "frontend/llm_model_scores/probe_providers_requested": Operation(
        payload_model=EmptyPayload, fn=op_llm_model_scores_probe_providers
    ),
    "frontend/ai_providers/snapshot_requested": Operation(
        payload_model=AIProvidersSnapshotPayload, fn=op_ai_providers_snapshot
    ),
    "frontend/ai_providers/llm_context_update_requested": Operation(
        payload_model=LLMContextPatch, fn=op_ai_providers_llm_context_update
    ),
    "frontend/ai_providers/llm_context_remove_requested": Operation(
        payload_model=EmptyPayload, fn=op_ai_providers_llm_context_remove
    ),
    "frontend/ai_providers/capability_update_requested": Operation(
        payload_model=AIProvidersCapabilityPayload, fn=op_ai_providers_capability_update
    ),
    "frontend/ai_providers/capability_remove_requested": Operation(
        payload_model=AIProvidersCapabilityIdPayload, fn=op_ai_providers_capability_remove
    ),
    "frontend/ai_providers/custom_create_requested": Operation(
        payload_model=CustomProviderCreate, fn=op_ai_providers_custom_create
    ),
    "frontend/ai_providers/custom_update_requested": Operation(
        payload_model=CustomProviderUpdatePayload, fn=op_ai_providers_custom_update
    ),
    "frontend/ai_providers/custom_remove_requested": Operation(
        payload_model=CustomProviderIdPayload, fn=op_ai_providers_custom_remove
    ),
    "frontend/ai_providers/resolved_requested": Operation(
        payload_model=EmptyPayload, fn=op_ai_providers_resolved
    ),
    "frontend/embed_configs/create_requested": Operation(
        payload_model=CreateEmbedConfigRequest, fn=op_embed_configs_create
    ),
    "frontend/embed_configs/list_requested": Operation(
        payload_model=EmbedConfigsListPayload, fn=op_embed_configs_list
    ),
    "frontend/embed_configs/item_requested": Operation(payload_model=EmbedIdPayload, fn=op_embed_configs_item),
    "frontend/embed_configs/update_requested": Operation(
        payload_model=EmbedConfigUpdatePayload, fn=op_embed_configs_update
    ),
    "frontend/embed_configs/remove_requested": Operation(payload_model=EmbedIdPayload, fn=op_embed_configs_remove),
    "frontend/embed_configs/code_requested": Operation(payload_model=EmbedCodePayload, fn=op_embed_configs_code),
    "frontend/lead_requests/list_requested": Operation(payload_model=LeadRequestsListPayload, fn=op_lead_requests_list),
    "frontend/agent/pairing_create_requested": Operation(
        payload_model=EmptyPayload, fn=op_agent_pairing_create
    ),
    "frontend/agent/devices_list_requested": Operation(
        payload_model=AgentDevicesListPayload, fn=op_agent_devices_list
    ),
    "frontend/agent/device_revoke_requested": Operation(
        payload_model=AgentDeviceIdPayload, fn=op_agent_devices_revoke
    ),
    "frontend/agent/device_policy_update_requested": Operation(
        payload_model=AgentDevicePolicyUpdatePayload, fn=op_agent_devices_policy_update
    ),
    "frontend/agent/audit_list_requested": Operation(payload_model=AgentAuditListPayload, fn=op_agent_audit_list),
}
