"""
Контракты Browser Runtime, общие для apps/browser (сервер) и apps/flows
(клиент через MCP). Живут в core/, чтобы flows не импортировал apps/browser
напрямую (нарушение peer-границы в architecture.mdc).
"""

from core.clients.browser.mcp_contracts import (
    ToolCloseSessionArgs,
    ToolCreateSessionArgs,
    ToolNavigateArgs,
    ToolObserveArgs,
    ToolSaveStateArgs,
)

__all__ = [
    "ToolCloseSessionArgs",
    "ToolCreateSessionArgs",
    "ToolNavigateArgs",
    "ToolObserveArgs",
    "ToolSaveStateArgs",
]
