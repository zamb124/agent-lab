"""Каталог команд Secrets: `secrets/variables/*` для WS RPC и REST-зеркала."""

from __future__ import annotations

from apps.secrets.container import SecretsContainer, get_secrets_container
from apps.secrets.realtime.operations import (
    SecretsVariableKeyPayload,
    SecretsVariablesListPayload,
    SecretsVariableVersionsPayload,
    op_variables_create,
    op_variables_item,
    op_variables_list,
    op_variables_remove,
    op_variables_resolve,
    op_variables_versions,
)
from core.logging import get_logger
from core.secrets.models import VariableResolveRequest, VariableWriteRequest
from core.websocket import Operation, RegisteredOperation, register_service_operations

logger = get_logger(__name__)

SECRETS_OPERATIONS: dict[str, RegisteredOperation[SecretsContainer]] = {
    "secrets/variables/list_requested": Operation(
        payload_model=SecretsVariablesListPayload, fn=op_variables_list
    ),
    "secrets/variables/item_requested": Operation(
        payload_model=SecretsVariableKeyPayload, fn=op_variables_item
    ),
    "secrets/variables/create_requested": Operation(
        payload_model=VariableWriteRequest, fn=op_variables_create
    ),
    "secrets/variables/remove_requested": Operation(
        payload_model=SecretsVariableKeyPayload, fn=op_variables_remove
    ),
    "secrets/variables/versions_requested": Operation(
        payload_model=SecretsVariableVersionsPayload, fn=op_variables_versions
    ),
    "secrets/variables/resolve_requested": Operation(
        payload_model=VariableResolveRequest, fn=op_variables_resolve
    ),
}


def register_secrets_ws_commands() -> None:
    register_service_operations(SECRETS_OPERATIONS, get_secrets_container)
    logger.info("command_router.registered", service="secrets", operations=len(SECRETS_OPERATIONS))
