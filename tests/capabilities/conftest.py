from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest

from core.capabilities import CAPABILITY_LANGUAGES
from tests.capabilities.capability_language_helpers import tool_payloads


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
