"""Smoke: worktracker.* capabilities via capability-gateway + живой worktracker."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from apps.capability_gateway.container import get_capability_gateway_container
from apps.capability_gateway.services.worktracker_capabilities import (
    WORKTRACKER_CLIENT_METHOD_NAMES,
)
from apps.flows.src.clients.worktracker_client import WorktrackerClient
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

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("worktracker_http_service")]


@contextmanager
def _company_context(*, user: User, company: Company) -> Iterator[None]:
    previous = get_context()
    ctx = build_job_context(
        company=company,
        user=user,
        host="",
        trace_id="worktracker-capability-test",
        session_id="worktracker-capability",
        channel="test",
    )
    set_context(ctx)
    try:
        yield
    finally:
        if previous is None:
            clear_context()
        else:
            set_context(previous)


def _execution_context() -> CapabilityExecutionContext:
    claims = CapabilityExecutionTokenClaims(
        company_id="system",
        user_id="system",
        flow_id="worktracker-capability-smoke",
        branch_id="main",
        session_id="worktracker-capability-smoke:ctx",
        task_id="task-worktracker-capability",
        context_id="ctx-worktracker-capability",
        channel="test",
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
    )


async def test_worktracker_capabilities_cover_client_methods() -> None:
    container = get_capability_gateway_container()
    manifest = await container.capability_registry.manifest()
    names = {item.name for item in manifest.capabilities}
    expected = {f"worktracker.{method}" for method in WORKTRACKER_CLIENT_METHOD_NAMES}
    assert expected <= names
    public_methods = {
        name
        for name in dir(WorktrackerClient)
        if not name.startswith("_") and callable(getattr(WorktrackerClient, name))
    }
    assert WORKTRACKER_CLIENT_METHOD_NAMES <= public_methods
    assert "get_queue_by_slug" in public_methods
    assert "get_queue_by_slug" not in WORKTRACKER_CLIENT_METHOD_NAMES


async def test_worktracker_capability_create_and_get(
    frontend_container,
    unique_id: str,
) -> None:
    company = await frontend_container.company_repository.get("system")
    assert company is not None
    user = await frontend_container.user_repository.get("system")
    assert user is not None
    title = f"Capability task {unique_id}"
    container = get_capability_gateway_container()
    registry = container.capability_registry
    context = _execution_context()

    with _company_context(user=user, company=company):
        created_response = await registry.call(
            CapabilityCallRequest(
                context=context,
                name="worktracker.create_manual_task",
                kwargs={"title": title},
            )
        )
    assert created_response.status == "ok", created_response
    created = created_response.result
    assert isinstance(created, dict)
    work_item_id = created.get("work_item_id")
    assert isinstance(work_item_id, str) and work_item_id.strip()
    assert created.get("title") == title

    got_response = await registry.call(
        CapabilityCallRequest(
            context=context,
            name="worktracker.get",
            kwargs={"work_item_id": work_item_id},
        )
    )
    assert got_response.status == "ok", got_response
    got = got_response.result
    assert isinstance(got, dict)
    assert got.get("work_item_id") == work_item_id
    assert got.get("title") == title


async def test_python_code_node_worktracker_create_and_get(
    worktracker_http_service,
    flows_client_http,
    auth_headers_system,
    unique_id: str,
) -> None:
    _ = worktracker_http_service
    title = f"Code node task {unique_id}"
    code = (
        "async def run(args, state):\n"
        "    created = await worktracker.create_manual_task(title=args['title'])\n"
        "    got = await worktracker.get(work_item_id=created['work_item_id'])\n"
        "    return {'work_item_id': got['work_item_id'], 'title': got['title']}\n"
    )
    response = await flows_client_http.post(
        "/flows/api/v1/code/execute",
        json={
            "node_type": "code",
            "node_config": {"type": "code", "language": "python", "code": code},
            "state": {},
            "args": {"title": title},
        },
        headers=auth_headers_system,
        timeout=180.0,
    )
    response.raise_for_status()
    body = response.json()
    assert body["success"] is True, body
    assert body["output_state"]["work_item_id"]
    assert body["output_state"]["title"] == title
