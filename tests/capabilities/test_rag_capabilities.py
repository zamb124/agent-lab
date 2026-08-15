"""Smoke: rag.* capabilities via capability-gateway + живой RAG."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from apps.capability_gateway.container import get_capability_gateway_container
from apps.capability_gateway.services.rag_capabilities import RAG_CLIENT_METHOD_NAMES
from core.capabilities import (
    CapabilityCallRequest,
    CapabilityExecutionContext,
    CapabilityExecutionTokenClaims,
    execution_token_exp,
    issue_execution_token,
)
from core.clients.rag_client import RagClient
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.models.identity_models import Company, User
from tests.sync.api._helpers import seed_namespace_via_repo

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("rag_service")]


@contextmanager
def _namespace_context(*, user: User, company: Company, namespace: str) -> Iterator[None]:
    previous = get_context()
    ctx = build_job_context(
        company=company,
        user=user,
        host="",
        trace_id="rag-capability-test",
        session_id="rag-capability",
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
        flow_id="rag-capability-smoke",
        branch_id="main",
        session_id="rag-capability-smoke:ctx",
        task_id="task-rag-capability",
        context_id="ctx-rag-capability",
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


async def test_rag_capabilities_cover_every_client_method() -> None:
    container = get_capability_gateway_container()
    manifest = await container.capability_registry.manifest()
    names = {item.name for item in manifest.capabilities}
    expected = {f"rag.{method}" for method in RAG_CLIENT_METHOD_NAMES}
    assert expected <= names
    public_methods = {
        name
        for name in dir(RagClient)
        if not name.startswith("_") and callable(getattr(RagClient, name))
    }
    public_methods.discard("files_download_url_path")
    assert RAG_CLIENT_METHOD_NAMES <= public_methods


async def test_rag_capability_create_namespace_and_ingest_text(
    frontend_container,
    unique_id: str,
) -> None:
    company = await frontend_container.company_repository.get("system")
    assert company is not None
    user = await frontend_container.user_repository.get("system")
    assert user is not None
    namespace = f"rag_cap_{unique_id}"
    await seed_namespace_via_repo("system", namespace)
    container = get_capability_gateway_container()
    registry = container.capability_registry
    context = _execution_context(namespace=namespace)

    with _namespace_context(user=user, company=company, namespace=namespace):
        created_response = await registry.call(
            CapabilityCallRequest(
                context=context,
                name="rag.create_namespace",
                kwargs={"name": namespace, "description": "capability smoke"},
            )
        )
    assert created_response.status == "ok", created_response
    created = created_response.result
    assert isinstance(created, dict)
    assert created.get("name") == namespace

    ingest_response = await registry.call(
        CapabilityCallRequest(
            context=context,
            name="rag.ingest_text",
            kwargs={
                "namespace_id": namespace,
                "collection_id": "smoke",
                "text": "Capability gateway indexed this fragment.",
                "document_name": "cap.txt",
            },
        )
    )
    assert ingest_response.status == "ok", ingest_response
    ingested = ingest_response.result
    assert isinstance(ingested, dict)
    assert ingested.get("namespace_id") == namespace
    assert ingested.get("status") == "completed"
    document_id = ingested.get("document_id")
    assert isinstance(document_id, str) and document_id.strip()


async def test_python_code_node_rag_create_namespace(
    rag_service,
    flows_client_http,
    auth_headers_system,
    unique_id: str,
) -> None:
    _ = rag_service
    namespace = f"rag_code_{unique_id}"
    code = (
        "async def run(args, state):\n"
        "    created = await rag.create_namespace(\n"
        "        name=args['name'],\n"
        "        description='code node',\n"
        "    )\n"
        "    ingested = await rag.ingest_text(\n"
        "        namespace_id=created['name'],\n"
        "        collection_id='code',\n"
        "        text='Indexed from code_node.',\n"
        "        document_name='code.txt',\n"
        "    )\n"
        "    return {'name': created['name'], 'status': ingested['status']}\n"
    )
    response = await flows_client_http.post(
        "/flows/api/v1/code/execute",
        json={
            "node_type": "code",
            "node_config": {"type": "code", "language": "python", "code": code},
            "state": {},
            "args": {"name": namespace},
        },
        headers=auth_headers_system,
        timeout=180.0,
    )
    response.raise_for_status()
    body = response.json()
    assert body["success"] is True, body
    assert body["output_state"]["name"] == namespace
    assert body["output_state"]["status"] == "completed"
