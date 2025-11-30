"""
Frontend API роутер - объединяет все суброутеры frontend API.

Итоговые пути:
- HTML страницы (modules/pages): /frontend/...
- JSON API (api/): /frontend/api/...
"""

from fastapi import APIRouter

# Импорт всех frontend API суброутеров
import apps.frontend.api.models as frontend_models
import apps.frontend.api.flows as frontend_flows
import apps.frontend.api.agents as frontend_agents
import apps.frontend.api.tools as frontend_tools
import apps.frontend.api.variables as frontend_variables
import apps.frontend.api.i18n as frontend_i18n
import apps.frontend.api.code as frontend_code
import apps.frontend.api.websocket_status as websocket_status_api
import apps.frontend.api.checkpoints as frontend_checkpoints
import apps.frontend.api.history as frontend_history

# Создание главного frontend API роутера с prefix /api
router = APIRouter(prefix="/api", tags=["frontend-api"])

# Включение суброутеров
router.include_router(frontend_history.router, tags=["frontend-history"], include_in_schema=False)
router.include_router(frontend_models.router, tags=["frontend-models"], include_in_schema=False)
router.include_router(frontend_flows.router, tags=["frontend-flows"], include_in_schema=False)
router.include_router(frontend_agents.router, tags=["frontend-agents"], include_in_schema=False)
router.include_router(frontend_tools.router, tags=["frontend-tools"], include_in_schema=False)
router.include_router(frontend_variables.router, tags=["frontend-variables"], include_in_schema=False)
router.include_router(frontend_i18n.router, prefix="/i18n", tags=["frontend-i18n"], include_in_schema=False)
router.include_router(frontend_code.router, tags=["frontend-code"], include_in_schema=False)
router.include_router(websocket_status_api.router, tags=["websocket-status"], include_in_schema=False)
router.include_router(frontend_checkpoints.router, tags=["frontend-checkpoints"], include_in_schema=False)
