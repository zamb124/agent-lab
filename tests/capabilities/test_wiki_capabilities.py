"""Smoke: wiki.* capabilities via capability-gateway + ASGI wiki."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from apps.capability_gateway.container import get_capability_gateway_container
from core.capabilities import (
    CapabilityCallRequest,
    CapabilityExecutionContext,
    CapabilityExecutionTokenClaims,
    execution_token_exp,
    issue_execution_token,
)
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.models.identity_models import Company, User
from tests.sync.api._helpers import seed_namespace_via_repo

pytest_plugins = ["tests.wiki.conftest"]
pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("wiki_app")]


@contextmanager
def _namespace_context(*, user: User, company: Company, namespace: str) -> Iterator[None]:
    previous = get_context()
    ctx = build_job_context(
        company=company,
        user=user,
        host="",
        trace_id="wiki-capability-test",
        session_id="wiki-capability",
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


def _execution_context(*, namespace: str) -> CapabilityExecutionContext:
    claims = CapabilityExecutionTokenClaims(
        company_id="system",
        user_id="system",
        flow_id="wiki-capability-smoke",
        branch_id="main",
        session_id="wiki-capability-smoke:ctx",
        task_id="task-wiki-capability",
        context_id="ctx-wiki-capability",
        channel="test",
        namespace=namespace,
        exp=execution_token_exp(120),
    )
    token = issue_execution_token(claims)
    return CapabilityExecutionContext(
        execution_token=token,
        company_id=claims.company_id,
        user_id=claims.user_id,
        flow_id=claims.flow_id,
        branch_id=claims.branch_id,
        session_id=claims.session_id,
        task_id=claims.task_id,
        context_id=claims.context_id,
        channel=claims.channel,
        namespace=namespace,
    )


async def test_wiki_capabilities_in_manifest() -> None:
    container = get_capability_gateway_container()
    manifest = await container.capability_registry.manifest()
    names = {item.name for item in manifest.capabilities}
    assert "wiki.create_page" in names
    assert "wiki.get_markdown" in names
    wiki_names = {name for name in names if name.startswith("wiki.")}
    assert len(wiki_names) >= 20


async def test_wiki_capability_create_and_get_markdown(
    frontend_container,
    unique_id: str,
) -> None:
    company = await frontend_container.company_repository.get("system")
    assert company is not None
    user = await frontend_container.user_repository.get("system")
    assert user is not None
    namespace = f"wiki-cap-{unique_id}"
    await seed_namespace_via_repo("system", namespace)

    container = get_capability_gateway_container()
    registry = container.capability_registry
    context = _execution_context(namespace=namespace)

    with _namespace_context(user=user, company=company, namespace=namespace):
        created_response = await registry.call(
            CapabilityCallRequest(
                context=context,
                name="wiki.create_page",
                kwargs={
                    "title": "Capability page",
                    "markdown": "# From capability",
                },
            )
        )
    assert created_response.status == "ok"
    created = created_response.result
    assert isinstance(created, dict)
    wiki_page_id = created.get("wiki_page_id")
    assert isinstance(wiki_page_id, str) and wiki_page_id.strip()

    markdown_response = await registry.call(
        CapabilityCallRequest(
            context=context,
            name="wiki.get_markdown",
            kwargs={"wiki_page_id": wiki_page_id},
        )
    )
    assert markdown_response.status == "ok"
    body = markdown_response.result
    assert isinstance(body, dict)
    assert body.get("wiki_page_id") == wiki_page_id
    assert "From capability" in str(body.get("markdown"))
