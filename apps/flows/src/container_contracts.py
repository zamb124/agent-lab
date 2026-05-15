"""Structural contracts for flows runtime dependencies."""

from __future__ import annotations

from typing import Any, Protocol


class FlowRuntimeContainer(Protocol):
    redis_client: Any
    flow_repository: Any
    flow_factory: Any
    state_manager: Any
    variables_service: Any
    resource_repository: Any
    resource_resolver: Any
    tool_repository: Any
    tool_registry: Any
    mcp_server_repository: Any
    channel_registry: Any
    operator_repository: Any
    operator_handoff_service: Any
    a2a_client: Any
    billing_service: Any
    safe_eval_class: type[Any]

    def get_code_runner(self, language: str = "python", resources: dict[str, object] | None = None) -> Any: ...
