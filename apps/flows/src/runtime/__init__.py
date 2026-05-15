"""Public runtime package interface.

The package itself must stay import-light: many modules import leaf runtime
modules such as ``runtime.exceptions`` while state/channels are still loading.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "Flow",
    "BaseNode",
    "LlmNode",
    "CodeNode",
    "FlowNode",
    "RemoteFlowNode",
    "ExternalAPINode",
    "create_node",
    "FlowInterrupt",
    "BreakpointInterrupt",
    "BaseLlmNodeRunner",
    "LlmNodeRunner",
    "SimpleLlmNodeExecutor",
]


def __getattr__(name: str) -> Any:
    if name == "Flow":
        from apps.flows.src.runtime.flow import Flow

        return Flow
    if name in {
        "BaseNode",
        "LlmNode",
        "CodeNode",
        "FlowNode",
        "RemoteFlowNode",
        "ExternalAPINode",
        "create_node",
    }:
        from apps.flows.src.runtime import nodes

        return getattr(nodes, name)
    if name in {"FlowInterrupt", "BreakpointInterrupt"}:
        from apps.flows.src.runtime import exceptions

        return getattr(exceptions, name)
    if name in {"BaseLlmNodeRunner", "LlmNodeRunner"}:
        from apps.flows.src.runtime import runners

        return getattr(runners, name)
    if name == "SimpleLlmNodeExecutor":
        from apps.flows.src.runtime.simple_executor import SimpleLlmNodeExecutor

        return SimpleLlmNodeExecutor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
