"""Prod-like: Evaluation Lab — REST и `op_*` один handler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx import AsyncClient

from apps.flows.realtime.evaluation_operations import (
    op_flows_evaluation_case_create,
    op_flows_evaluation_cases_list,
    op_flows_evaluation_evaluator_catalog,
    op_flows_evaluation_suite_archive,
    op_flows_evaluation_suite_create,
    op_flows_evaluation_suite_item,
    op_flows_evaluation_suites_list,
)
from apps.flows.src.container import FlowContainer
from apps.flows.src.models.evaluation_lab import (
    EvaluationBuiltinEvaluatorCatalog,
    EvaluationCase,
    EvaluationCaseCreateRequest,
    EvaluationCheckContains,
    EvaluationFlowIdPayload,
    EvaluationInputText,
    EvaluationSuite,
    EvaluationSuiteCreateRequest,
    EvaluationSuiteIdPayload,
    EvaluationTurn,
)
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from core.pagination import ListResponse
from core.websocket import EmptyPayload, WsCommandError
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]


@contextmanager
def _system_scope(system_user_id: str) -> Generator[User]:
    user = User(user_id=system_user_id, name="System")
    token = set_context(
        Context(
            user=user,
            active_company=make_test_company(company_id="system", name="System"),
            channel="api",
        )
    )
    try:
        yield user
    finally:
        reset_context(token)


async def _create_eval_flow(client: AsyncClient, flow_id: str, headers: dict[str, str]) -> None:
    created = await client.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": "Evaluation command flow",
            "entry": "echo",
            "nodes": {
                "echo": {
                    "type": "code",
                    "code": (
                        "async def run(args, state):\n"
                        "    state['response'] = f\"Echo: {state['content']}\"\n"
                        "    return state\n"
                    ),
                }
            },
            "edges": [{"from_node": "echo", "to_node": None}],
        },
    )
    assert created.status_code == 200, created.text


def _case_payload(*, name: str) -> dict[str, object]:
    return {
        "name": name,
        "description": "command case",
        "branch_ids": "*",
        "turns": [
            {
                "input": {"type": "text", "content": "ping"},
                "checks": [{"type": "contains", "values": ["Echo"]}],
            }
        ],
    }


async def test_evaluation_catalog_and_suite_rest_match_op(
    client: AsyncClient,
    container: FlowContainer,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    flow_id = f"eval_cmd_{unique_id}"
    await _create_eval_flow(client, flow_id, auth_headers_system)

    catalog_http = await client.get(
        "/flows/api/v1/evaluation/evaluator-catalog",
        headers=auth_headers_system,
    )
    assert catalog_http.status_code == 200, catalog_http.text
    _ = EvaluationBuiltinEvaluatorCatalog.model_validate(catalog_http.json())

    suite_http = await client.post(
        "/flows/api/v1/evaluation/suites",
        headers=auth_headers_system,
        json={
            "flow_id": flow_id,
            "name": "Command suite",
            "description": "rest+op",
            "tags": ["cmd"],
        },
    )
    assert suite_http.status_code == 200, suite_http.text
    suite = EvaluationSuite.model_validate(suite_http.json())
    assert suite.flow_id == flow_id
    assert suite.name == "Command suite"

    case_http = await client.post(
        f"/flows/api/v1/evaluation/suites/{suite.suite_id}/cases",
        headers=auth_headers_system,
        json=_case_payload(name="First case"),
    )
    assert case_http.status_code == 200, case_http.text
    case = EvaluationCase.model_validate(case_http.json())
    assert case.suite_id == suite.suite_id
    assert case.name == "First case"

    list_http = await client.get(
        "/flows/api/v1/evaluation/suites",
        headers=auth_headers_system,
        params={"flow_id": flow_id},
    )
    assert list_http.status_code == 200, list_http.text

    cases_http = await client.get(
        f"/flows/api/v1/evaluation/suites/{suite.suite_id}/cases",
        headers=auth_headers_system,
    )
    assert cases_http.status_code == 200, cases_http.text

    with _system_scope(system_user_id) as user:
        catalog = await op_flows_evaluation_evaluator_catalog(
            EmptyPayload(),
            user=user,
            container=container,
        )
        assert catalog.model_dump(mode="json") == catalog_http.json()
        listed = await op_flows_evaluation_suites_list(
            EvaluationFlowIdPayload(flow_id=flow_id),
            user=user,
            container=container,
        )
        assert listed.model_dump(mode="json") == list_http.json()
        item = await op_flows_evaluation_suite_item(
            EvaluationSuiteIdPayload(suite_id=suite.suite_id),
            user=user,
            container=container,
        )
        assert item.model_dump(mode="json") == suite_http.json()
        cases = await op_flows_evaluation_cases_list(
            EvaluationSuiteIdPayload(suite_id=suite.suite_id),
            user=user,
            container=container,
        )
        assert cases.model_dump(mode="json") == cases_http.json()
        _ = ListResponse[EvaluationSuite].model_validate(list_http.json())

    missing = await client.get(
        f"/flows/api/v1/evaluation/suites/missing-{unique_id}",
        headers=auth_headers_system,
    )
    assert missing.status_code == 404, missing.text

    with _system_scope(system_user_id) as user:
        with pytest.raises(WsCommandError) as exc_info:
            _ = await op_flows_evaluation_suite_item(
                EvaluationSuiteIdPayload(suite_id=f"missing-{unique_id}"),
                user=user,
                container=container,
            )
    assert exc_info.value.code == "not_found"

    _ = await client.delete(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)


async def test_evaluation_suite_create_and_archive_via_op(
    client: AsyncClient,
    container: FlowContainer,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    flow_id = f"eval_cmd_op_{unique_id}"
    await _create_eval_flow(client, flow_id, auth_headers_system)

    with _system_scope(system_user_id) as user:
        created = await op_flows_evaluation_suite_create(
            EvaluationSuiteCreateRequest(
                flow_id=flow_id,
                name="Op suite",
                description="",
                tags=[],
            ),
            user=user,
            container=container,
        )
        case = await op_flows_evaluation_case_create(
            EvaluationCaseCreateRequest(
                suite_id=created.suite_id,
                name="Op case",
                description="",
                branch_ids="*",
                turns=[
                    EvaluationTurn(
                        input=EvaluationInputText(type="text", content="ping"),
                        checks=[EvaluationCheckContains(type="contains", values=["Echo"])],
                    )
                ],
            ),
            user=user,
            container=container,
        )
        assert case.suite_id == created.suite_id
        archived = await op_flows_evaluation_suite_archive(
            EvaluationSuiteIdPayload(suite_id=created.suite_id),
            user=user,
            container=container,
        )
        assert archived.archived_at is not None

    fetched = await client.get(
        f"/flows/api/v1/evaluation/suites/{created.suite_id}",
        headers=auth_headers_system,
    )
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["archived_at"] is not None

    _ = await client.delete(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)
