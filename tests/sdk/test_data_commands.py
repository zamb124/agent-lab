"""CLI индексирует файл в RAG и читает список провайдеров поиска."""

from __future__ import annotations

from pathlib import Path

import pytest
from platform_sdk.commands import cmd_rag_index, cmd_rag_ns, cmd_rag_search, cmd_search_providers
from platform_sdk.context_store import PlatformContext
from platform_sdk.http import PlatformClient

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(90)]


def _client(http_client, headers: dict[str, str]) -> PlatformClient:
    token = headers["Authorization"].removeprefix("Bearer ").strip()
    context = PlatformContext(
        name="test", host="http://test", api_key=token, company_subdomain="system"
    )
    return PlatformClient(context, timeout=60, http=http_client)


async def test_rag_index_then_search(
    rag_client,
    auth_headers_system: dict[str, str],
    unique_namespace_name: str,
    unique_id: str,
    tmp_path: Path,
) -> None:
    sdk = _client(rag_client, auth_headers_system)
    created = await cmd_rag_ns(sdk, unique_namespace_name, "cli")
    assert created == 0
    document = tmp_path / "note.txt"
    marker = f"platform-cli-marker-{unique_id}"
    document.write_text(f"Python notes {marker}\n", encoding="utf-8")
    assert (
        await cmd_rag_index(
            sdk,
            namespace=unique_namespace_name,
            path=document,
            file_id=None,
            wait=True,
            timeout=60,
        )
        == 0
    )
    assert await cmd_rag_search(sdk, unique_namespace_name, marker, 5) == 0


async def test_search_providers_returns_json(
    search_client, auth_headers_system: dict[str, str]
) -> None:
    sdk = _client(search_client, auth_headers_system)
    assert await cmd_search_providers(sdk) == 0
