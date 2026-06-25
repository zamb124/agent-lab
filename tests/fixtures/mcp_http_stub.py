"""
Backward-compatible re-export MCP stub fixtures.

Реализация — `tests.fixtures.mcp_modes_stub`.
"""

from tests.fixtures.mcp_modes_stub import (  # noqa: F401
    MCPStubMode,
    MCPStubState,
    default_stub_tools,
    default_tool_call_success,
    local_mcp_http_url,
    mcp_modes_stub,
    mcp_modes_stub_session,
)
