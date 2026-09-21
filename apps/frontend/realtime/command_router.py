"""Регистрация WS command-handler'ов frontend в `core.websocket`."""

from __future__ import annotations

from apps.frontend.container import FrontendContainer, get_frontend_container
from apps.frontend.realtime.operations import FrontendEmptyPayload, op_dashboard_stats
from core.logging import get_logger
from core.websocket import Operation, RegisteredOperation, register_service_operations

logger = get_logger(__name__)

FRONTEND_OPERATIONS: dict[str, RegisteredOperation[FrontendContainer]] = {
    "frontend/dashboard/stats_requested": Operation(payload_model=FrontendEmptyPayload, fn=op_dashboard_stats),
}


def register_frontend_ws_commands() -> None:
    register_service_operations(FRONTEND_OPERATIONS, get_frontend_container)
    logger.info("command_router.registered", service="frontend", operations=len(FRONTEND_OPERATIONS))
