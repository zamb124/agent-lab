"""Process-local lifecycle state for the Flows container."""

from __future__ import annotations

from apps.flows.src.container_contracts import FlowRuntimeContainer

_container: FlowRuntimeContainer | None = None


def get_current_container() -> FlowRuntimeContainer | None:
    return _container


def require_current_container() -> FlowRuntimeContainer:
    if _container is None:
        raise RuntimeError("FlowContainer is not initialized")
    return _container


def set_current_container(container: FlowRuntimeContainer) -> None:
    global _container
    _container = container


def reset_current_container() -> None:
    global _container
    _container = None
