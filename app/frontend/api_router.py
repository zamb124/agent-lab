"""
Frontend API роутер - объединяет все суброутеры frontend API
"""

from fastapi import APIRouter

# Импорт всех frontend API суброутеров
import app.frontend.api.models as frontend_models
import app.frontend.api.flows as frontend_flows
import app.frontend.api.agents as frontend_agents
import app.frontend.api.tools as frontend_tools
import app.frontend.api.variables as frontend_variables
import app.frontend.api.i18n as frontend_i18n
import app.frontend.api.code as frontend_code
import app.frontend.api.websocket_status as websocket_status_api
import app.frontend.api.checkpoints as frontend_checkpoints

# Создание главного frontend API роутера
router = APIRouter(tags=["frontend-api"])

# Включение суброутеров (без дополнительных префиксов, так как общий префикс "/frontend/api" добавляется в main.py)
router.include_router(frontend_models.router, tags=["frontend-models"], include_in_schema=False)
router.include_router(frontend_flows.router, tags=["frontend-flows"], include_in_schema=False)
router.include_router(frontend_agents.router, tags=["frontend-agents"], include_in_schema=False)
router.include_router(frontend_tools.router, tags=["frontend-tools"], include_in_schema=False)
router.include_router(frontend_variables.router, tags=["frontend-variables"], include_in_schema=False)
router.include_router(frontend_i18n.router, prefix="/i18n", tags=["frontend-i18n"], include_in_schema=False)
router.include_router(frontend_code.router, tags=["frontend-code"], include_in_schema=False)
router.include_router(websocket_status_api.router, tags=["websocket-status"], include_in_schema=False)
router.include_router(frontend_checkpoints.router, tags=["frontend-checkpoints"], include_in_schema=False)
