"""Smoke: documents.* capabilities via capability-gateway + ASGI office."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

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

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("office_app")]


@contextmanager
def _namespace_context(*, user: User, company: Company, namespace: str) -> Iterator[None]:
    previous = get_context()
    ctx = build_job_context(
        company=company,
        user=user,
        host="",
        trace_id="documents-capability-test",
        session_id="documents-capability",
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
        flow_id="documents-capability-smoke",
        branch_id="main",
        session_id="documents-capability-smoke:ctx",
        task_id="task-documents-capability",
        context_id="ctx-documents-capability",
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


async def test_documents_capabilities_in_manifest(capability_gateway_di) -> None:
    manifest = await capability_gateway_di.capability_registry.manifest()
    names = {item.name for item in manifest.capabilities}
    assert "documents.create_catalog" in names
    assert "documents.create_empty" in names
    assert "documents.find" in names
    documents_names = {name for name in names if name.startswith("documents.")}
    assert len(documents_names) >= 20


async def test_documents_capability_create_catalog_and_empty(
    frontend_di,
    unique_id: str,
capability_gateway_di) -> None:
    company = await Company.get("system")
    assert company is not None
    user = await User.get("system")
    assert user is not None
    namespace = f"docs-cap-{unique_id}"
    await seed_namespace_via_repo(frontend_di, "system", namespace)

    registry = capability_gateway_di.capability_registry
    context = _execution_context(namespace=namespace)

    with _namespace_context(user=user, company=company, namespace=namespace):
        catalog_response = await registry.call(
            CapabilityCallRequest(
                context=context,
                name="documents.create_catalog",
                kwargs={"title": f"Cap folder {unique_id}"},
            )
        )
    assert catalog_response.status == "ok"
    catalog = catalog_response.result
    assert isinstance(catalog, dict)
    catalog_id = catalog.get("catalog_id")
    assert isinstance(catalog_id, str) and catalog_id.strip()

    empty_response = await registry.call(
        CapabilityCallRequest(
            context=context,
            name="documents.create_empty",
            kwargs={
                "title": f"Cap doc {unique_id}",
                "catalog_id": catalog_id,
                "document_type": "word",
            },
        )
    )
    assert empty_response.status == "ok"
    created = empty_response.result
    assert isinstance(created, dict)
    file_id = created.get("file_id")
    assert isinstance(file_id, str) and file_id.strip()
    assert created.get("catalog_id") == catalog_id
