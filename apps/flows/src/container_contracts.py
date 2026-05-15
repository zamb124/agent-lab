"""Structural contracts for flows runtime dependencies."""

from __future__ import annotations

from typing import Any, Protocol


class FlowRuntimeContainer(Protocol):
    @property
    def redis_client(self) -> Any: ...

    @property
    def flow_repository(self) -> Any: ...

    @property
    def flow_factory(self) -> Any: ...

    @property
    def state_manager(self) -> Any: ...

    @property
    def variables_service(self) -> Any: ...

    @property
    def resource_repository(self) -> Any: ...

    @property
    def resource_resolver(self) -> Any: ...

    @property
    def node_repository(self) -> Any: ...

    @property
    def tool_repository(self) -> Any: ...

    @property
    def tool_registry(self) -> Any: ...

    @property
    def mcp_server_repository(self) -> Any: ...

    @property
    def channel_registry(self) -> Any: ...

    @property
    def operator_repository(self) -> Any: ...

    @property
    def operator_handoff_service(self) -> Any: ...

    @property
    def a2a_client(self) -> Any: ...

    @property
    def billing_service(self) -> Any: ...

    @property
    def file_processor(self) -> Any: ...

    @property
    def evaluation_service(self) -> Any: ...

    @property
    def base_tool_class(self) -> Any: ...

    def get_code_runner(
        self,
        language: str = "python",
        resources: dict[str, object] | None = None,
        variables: dict[str, object] | None = None,
    ) -> Any: ...
