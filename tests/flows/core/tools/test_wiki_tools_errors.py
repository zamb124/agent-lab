"""Wiki tools propagate client errors instead of success=false envelopes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from apps.flows.tools.wiki.wiki_tools import wiki_get_page
from core.clients.service_client import ServiceClientError
from core.clients.wiki_models import WikiPageIdArgs
from core.state import ExecutionState


@pytest.mark.asyncio
async def test_wiki_tool_raises_service_client_error() -> None:
    state = ExecutionState(
        task_id="task-1",
        context_id="ctx-1",
        user_id="user-1",
        session_id="flow:ctx-1",
    )
    args = WikiPageIdArgs(wiki_page_id="missing-page").model_dump(mode="json")
    with patch(
        "apps.flows.tools.wiki.wiki_tools.WikiClient.get_page",
        new=AsyncMock(
            side_effect=ServiceClientError(
                "HTTP 404",
                status_code=404,
                response_text='{"detail":"not found"}',
            )
        ),
    ):
        with pytest.raises(ServiceClientError):
            _ = await wiki_get_page.run(args, state)
