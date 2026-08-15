from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest

from apps.code_runner_csharp.services.lsp import csharp_lsp_command
from apps.code_runner_go.services.lsp import go_lsp_command
from apps.code_runner_node.services.lsp import node_lsp_command
from core.capabilities import CAPABILITY_LANGUAGES
from core.capabilities.lsp_commands import python_lsp_command
from tests.capabilities.capability_language_helpers import tool_payloads


@pytest.fixture(scope="session")
def code_lsp_toolchains_ready(sandbox_services: dict[str, str]) -> None:
    """Прогрев LSP cache: python/node/go/csharp language servers, один раз на сессию."""
    _ = sandbox_services
    _ = python_lsp_command()
    _ = node_lsp_command()
    _ = go_lsp_command()
    _ = csharp_lsp_command()


@pytest.fixture
async def cross_language_tool_ids(
    flows_client_http,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> AsyncGenerator[dict[str, str], None]:
    tool_ids = {
        language: f"cap_{language}_{unique_id}_{uuid4().hex[:8]}"
        for language in CAPABILITY_LANGUAGES
    }
    try:
        for payload in tool_payloads(tool_ids):
            response = await flows_client_http.post(
                "/flows/api/v1/tools/",
                json=payload,
                headers=auth_headers_system,
            )
            response.raise_for_status()
        yield tool_ids
    finally:
        for tool_id in tool_ids.values():
            await flows_client_http.delete(
                f"/flows/api/v1/tools/{tool_id}",
                headers=auth_headers_system,
            )
