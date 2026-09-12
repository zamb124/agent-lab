"""API v1 endpoints"""

from fastapi import APIRouter

from .agent_skills import router as agent_skills_router
from .agent_toolkits import router as agent_toolkits_router
from .browser_preview import router as browser_preview_router
from .certificate import router as certificate_router
from .code import router as code_router
from .code_lsp import router as code_lsp_router
from .company import router as company_router
from .data_tables import router as data_tables_router
from .datasources import router as datasources_router
from .evaluation import router as evaluation_router
from .flow_ui import router as flow_ui_router
from .flow_ui_shares import router as flow_ui_shares_router
from .flows import router as flows_router
from .hitl_conversation import router as hitl_conversation_router
from .internal_company import router as internal_company_router
from .lara_actions import router as lara_actions_router
from .llm_context import router as llm_context_router
from .mcp import router as mcp_router
from .metadata import router as metadata_router
from .nodes import router as nodes_router
from .observability_logs import router as observability_logs_router
from .platform_events import router as platform_events_router
from .prompts import router as prompts_router
from .resources import router as resources_router
from .sessions import router as sessions_router
from .tasks import router as tasks_router
from .tool_runtime import router as tool_runtime_router
from .tools import router as tools_router
from .traces import router as traces_router
from .triggers import router as triggers_router
from .voice_providers_catalog import router as flows_voice_providers_catalog_router
from .work_queues import router as work_queues_router

api_v1_router = APIRouter()

api_v1_router.include_router(agent_skills_router)
api_v1_router.include_router(agent_toolkits_router)
api_v1_router.include_router(flows_voice_providers_catalog_router)
api_v1_router.include_router(lara_actions_router)
api_v1_router.include_router(llm_context_router)
api_v1_router.include_router(flows_router, prefix="/flows")
api_v1_router.include_router(flow_ui_router)
api_v1_router.include_router(flow_ui_shares_router)
api_v1_router.include_router(certificate_router, prefix="/certificate")
api_v1_router.include_router(evaluation_router, prefix="/evaluation")
api_v1_router.include_router(metadata_router, prefix="/metadata")
api_v1_router.include_router(nodes_router, prefix="/nodes")
api_v1_router.include_router(sessions_router, prefix="/sessions")
api_v1_router.include_router(tools_router, prefix="/tools")
api_v1_router.include_router(tool_runtime_router, prefix="/tool-runtime")
api_v1_router.include_router(tasks_router, prefix="/tasks")
api_v1_router.include_router(traces_router, prefix="/traces")
api_v1_router.include_router(observability_logs_router, prefix="/observability/logs")
api_v1_router.include_router(platform_events_router, prefix="/platform-events")
api_v1_router.include_router(triggers_router)
api_v1_router.include_router(prompts_router, prefix="/prompts")
api_v1_router.include_router(code_router, prefix="/code")
api_v1_router.include_router(code_lsp_router, prefix="/code")
api_v1_router.include_router(company_router)
api_v1_router.include_router(data_tables_router)
api_v1_router.include_router(datasources_router)
api_v1_router.include_router(mcp_router, prefix="/mcp")
api_v1_router.include_router(resources_router, prefix="/resources")
api_v1_router.include_router(hitl_conversation_router)
api_v1_router.include_router(work_queues_router)
api_v1_router.include_router(internal_company_router, prefix="/internal")
api_v1_router.include_router(browser_preview_router, prefix="/browser-preview")
