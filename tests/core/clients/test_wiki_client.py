"""WikiClient against ASGI wiki service."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from core.clients.wiki_client import WikiClient
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.models.identity_models import Company, User
from tests.sync.api._helpers import seed_namespace_via_repo

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("wiki_app")]


@contextmanager
def _namespace_context(*, user: User, company: Company, namespace: str) -> Iterator[None]:
    previous = get_context()
    ctx = build_job_context(
        company=company,
        user=user,
        host="",
        trace_id="wiki-client-test",
        session_id="wiki-client",
        channel="test",
    )
    set_context(ctx.model_copy(update={"active_namespace": namespace}))
    try:
        yield
    finally:
        if previous is None:
            clear_context()
        else:
            set_context(previous)


async def test_wiki_client_create_page_and_get_markdown(
    frontend_container,
    unique_id: str,
) -> None:
    company = await frontend_container.company_repository.get("system")
    assert company is not None
    user = await frontend_container.user_repository.get("system")
    assert user is not None
    namespace = f"wiki-client-{unique_id}"
    await seed_namespace_via_repo("system", namespace)

    with _namespace_context(user=user, company=company, namespace=namespace):
        client = WikiClient()
        created = await client.create_page(
            title="Client page",
            markdown="# Hello wiki client",
        )
        wiki_page_id = created.get("wiki_page_id")
        assert isinstance(wiki_page_id, str) and wiki_page_id.strip()

        body = await client.get_markdown(wiki_page_id)
        assert body.get("wiki_page_id") == wiki_page_id
        assert body.get("title") == "Client page"
        assert "Hello wiki client" in str(body.get("markdown"))

        tree = await client.list_tree()
        assert tree.get("count") == 1
