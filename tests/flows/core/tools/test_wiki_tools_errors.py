"""Wiki tools propagate client errors instead of success=false envelopes."""

from __future__ import annotations

import pytest

from apps.flows.di import FlowsDi
from apps.flows.src.state import ExecutionState
from apps.flows.tools.wiki.wiki_tools import wiki_get_page
from core.clients.service_client import ServiceClientError
from core.clients.wiki_models import WikiPageIdArgs
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User


@pytest.mark.asyncio
async def test_wiki_tool_raises_service_client_error(
    di: FlowsDi,
    wiki_app: object,
    unique_id: str,
) -> None:
    _ = wiki_app
    user = await User.get("system")
    if user is None:
        raise RuntimeError("system user is required")
    company = await Company.get("system")
    if company is None:
        raise RuntimeError("system company is required")
    namespace = f"wiki-missing-{unique_id}"
    token = set_context(
        Context(
            user=user,
            active_company=company,
            session_id=f"wiki-tool-error-{unique_id}",
            channel="test",
            active_namespace=namespace,
        )
    )
    try:
        await di.namespace_service.get_or_create(
            namespace,
            description=f"Wiki missing page {unique_id}",
        )
        state = ExecutionState(
            task_id=f"task-{unique_id}",
            context_id=f"ctx-{unique_id}",
            user_id="system",
            session_id=f"flow:{unique_id}",
        )
        args = WikiPageIdArgs(wiki_page_id=f"missing-{unique_id}").model_dump(mode="json")
        with pytest.raises(ServiceClientError) as raised:
            _ = await wiki_get_page.run(args, state)
    finally:
        reset_context(token)

    assert raised.value.status_code == 404
