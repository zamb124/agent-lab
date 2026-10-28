"""E2E сценарии переменных: demo seed, scoped/expression/secret, branch replace."""

from __future__ import annotations

import pytest

from apps.flows.src.models import FlowConfig
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User
from core.variables.models import ResolutionContext
from core.variables.scenarios import DEMO_VARIABLE_KEYS, VariableScenario
from tests.flows.durable_runtime_harness import run_flow, workflow_state


def _system_context(*, user_id: str = "test_user", namespace: str = "default", channel: str = "test") -> Context:
    return Context(
        user=User(user_id=user_id, name="Test User"),
        active_company=Company(company_id="system", name="System"),
        active_namespace=namespace,
        session_id="test_session",
        channel=channel,
    )


@pytest.fixture(autouse=True)
async def ensure_demo_sales_namespace(di) -> None:
    """Scoped demo_greeting использует namespace=sales; Check — OpenFGA tuples через NamespaceService."""
    set_context(_system_context())
    try:
        _ = await di.namespace_service.get_or_create(
            "sales",
            description="Demo sales namespace for variable scope tests",
        )
    finally:
        clear_context()


@pytest.fixture(autouse=True)
async def ensure_demo_company_variables_seeded(di) -> None:
    """Идемпотентный demo seed перед каждым тестом — защита от загрязнения shared keys."""
    from apps.flows.src.services.demo_company_variables import seed_demo_company_variables

    set_context(_system_context())
    try:
        _ = await seed_demo_company_variables(di.variables_service, "system")
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_demo_seed_resolves_company_name(di, app) -> None:
    set_context(_system_context())
    try:
        resolved = await di.variables_service.resolve_for_run(
            ResolutionContext(company_id="system", user_id="test_user")
        )
        assert resolved[DEMO_VARIABLE_KEYS[VariableScenario.COMPANY_STATIC]] == "Humanitec Demo"
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_scoped_greeting_by_namespace(di, app) -> None:
    set_context(_system_context(namespace="sales"))
    try:
        resolved = await di.variables_service.resolve_for_run(
            ResolutionContext(company_id="system", user_id="test_user", namespace="sales")
        )
        assert resolved["demo_greeting"] == "Welcome to Sales"
    finally:
        clear_context()

    set_context(_system_context(namespace="default"))
    try:
        resolved = await di.variables_service.resolve_for_run(
            ResolutionContext(company_id="system", user_id="test_user", namespace="default")
        )
        assert resolved["demo_greeting"] == "Hello"
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_scoped_user_tier_by_user_id(di, app) -> None:
    set_context(_system_context(user_id="demo-premium-user"))
    try:
        resolved = await di.variables_service.resolve_for_run(
            ResolutionContext(company_id="system", user_id="demo-premium-user")
        )
        assert resolved["demo_user_tier"] == "premium"
        assert resolved["order_mode"] == "premium"
        assert resolved["order_limit"] == "unlimited"
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_expression_signature_resolves(di, app) -> None:
    set_context(_system_context())
    try:
        resolved = await di.variables_service.resolve_for_run(
            ResolutionContext(company_id="system", user_id="test_user")
        )
        assert resolved["signature"] == "-- Humanitec Demo Support"
        assert resolved["base_url"] == "https://api.demo.example.com/v1"
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_shared_secret_in_flow_variables(di, app) -> None:
    set_context(_system_context())
    try:
        flow = await di.flow_factory.get_flow("example_react", branch_id="default", tool_registry=di.tool_registry)
        assert flow is not None
        assert flow.variables["support_api_key"] == "demo-shared-api-key-12345"
        assert flow.variables["company_name"] == "Humanitec Demo"
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_branch_variables_replace_mode(di, app) -> None:
    set_context(_system_context())
    try:
        flow_config = await FlowConfig.current_for_flow("example_react")
        assert flow_config is not None
        effective = di.flow_factory.apply_branch(flow_config, "variables_replace")
        assert effective["variables"]["max_response_length"] == "100"
        assert "company_name" not in effective["variables"]
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_example_graph_greeting_uses_scoped_variables(app, unique_id: str, di) -> None:
    set_context(_system_context(namespace="sales"))
    try:
        flow = await di.flow_factory.get_flow("example_graph", tool_registry=di.tool_registry)
        state = workflow_state(
            flow_id="example_graph",
            unique_id=unique_id,
            content="привет",
        )
        result = await run_flow(di=di, flow=flow, state=state)
        assert result.get("route") == "greeting"
        response = str(result.get("response", ""))
        assert "Welcome to Sales" in response or "GREETING" in response
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_secret_keys_audit_list(di, app) -> None:
    set_context(_system_context())
    try:
        secret_keys = await di.variables_service.secret_variable_keys()
        assert "support_api_key" in secret_keys
        assert "private_owner_token" in secret_keys
    finally:
        clear_context()
