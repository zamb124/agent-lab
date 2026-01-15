"""API v1 endpoints"""

from fastapi import APIRouter

from .agents import router as agents_router
from .certificate import router as certificate_router
from .evaluation import router as evaluation_router
from .metadata import router as metadata_router
from .nodes import router as nodes_router
from .sessions import router as sessions_router
from .tasks import router as tasks_router
from .tools import router as tools_router
from .traces import router as traces_router
from .variables import router as variables_router
from .prompts import router as prompts_router
from .code import router as code_router
from .company import router as company_router
from .mcp import router as mcp_router

api_v1_router = APIRouter()

api_v1_router.include_router(agents_router, prefix="/agents")
api_v1_router.include_router(certificate_router, prefix="/certificate")
api_v1_router.include_router(evaluation_router, prefix="/evaluation")
api_v1_router.include_router(metadata_router, prefix="/metadata")
api_v1_router.include_router(nodes_router, prefix="/nodes")
api_v1_router.include_router(sessions_router, prefix="/sessions")
api_v1_router.include_router(tools_router, prefix="/tools")
api_v1_router.include_router(tasks_router, prefix="/tasks")
api_v1_router.include_router(traces_router, prefix="/traces")
api_v1_router.include_router(variables_router, prefix="/variables")
api_v1_router.include_router(prompts_router, prefix="/prompts")
api_v1_router.include_router(code_router, prefix="/code")
api_v1_router.include_router(company_router)
api_v1_router.include_router(mcp_router, prefix="/mcp")
