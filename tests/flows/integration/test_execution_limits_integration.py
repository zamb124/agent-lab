"""
Интеграционные проверки wall-clock лимитов flows: реальные Flow, CodeNode, Redis, HTTP.

Без unittest.mock и без подмены check_cancellation / wait_for / Pydantic.

Покрывается: дедлайн run в state, приоритет wall-clock над Redis, node asyncio.wait_for,
кламп дедлайна к cap из настроек, отклонение завышенных timeout в FlowConfig/NodeConfig,
валидация entrypoint по HTTP, ошибка node timeout в /code/execute,
инвариант default_flow_timeout_seconds.

Не покрывается тестами (в принципе): чистый CPU-bound бесконечный цикл в том же
потоке (asyncio wait_for не прерывает), токены отмены без Redis в другом процессе;
это соответствует разделу «ограничения» в плане лимитов.
"""

from __future__ import annotations
import time
import pytest
from apps.flows.config import get_settings
from apps.flows.src.constants.execution_limits import (
    get_flow_execution_wall_time_cap_seconds,
    get_graph_max_iterations,
    get_node_execution_wall_time_cap_seconds,
)
from apps.flows.src.models.flow_config import FlowConfig, FlowType
from apps.flows.src.models.node_config import NodeConfig
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import CodeNode
from apps.flows.src.state.cancellation import (
    CancellationToken,
    FlowCancelled,
    check_cancellation,
    set_cancellation_token,
)
from apps.flows.src.state.flow_deadline import apply_flow_wall_clock_deadline
from core.errors import FlowWallClockTimeoutError, NodeWallClockTimeoutError


@pytest.mark.asyncio
async def test_check_cancellation_raises_flow_wall_clock_when_deadline_passed(
    app, make_test_state, unique_id: str
) -> None:
    state = make_test_state(
        task_id=f"task-{unique_id}",
        context_id=f"ctx-{unique_id}",
        session_id=f"flow_cap_{unique_id}:ctx-{unique_id}",
    )
    state.flow_deadline_monotonic = time.monotonic() - 1.0
    state.flow_timeout_effective_seconds = 77
    with pytest.raises(FlowWallClockTimeoutError) as exc_info:
        await check_cancellation(state)
    assert exc_info.value.payload["flow_id"] == f"flow_cap_{unique_id}"
    assert exc_info.value.payload["timeout_seconds"] == 77
    assert exc_info.value.code == "FLOW_WALL_CLOCK_TIMEOUT"


@pytest.mark.asyncio
async def test_check_cancellation_uses_default_flow_timeout_when_effective_unset(
    app, make_test_state, unique_id: str
) -> None:
    state = make_test_state(
        task_id=f"task-{unique_id}",
        context_id=f"ctx-{unique_id}",
        session_id=f"flow_def_{unique_id}:ctx-{unique_id}",
    )
    state.flow_deadline_monotonic = time.monotonic() - 0.5
    state.flow_timeout_effective_seconds = None
    with pytest.raises(FlowWallClockTimeoutError) as exc_info:
        await check_cancellation(state)
    assert exc_info.value.payload["timeout_seconds"] == get_settings().default_flow_timeout_seconds


@pytest.mark.asyncio
async def test_check_cancellation_does_not_raise_when_deadline_in_future(
    app, make_test_state, unique_id: str
) -> None:
    state = make_test_state(
        task_id=f"task-{unique_id}",
        context_id=f"ctx-{unique_id}",
        session_id=f"flow_ok_{unique_id}:ctx-{unique_id}",
    )
    state.flow_deadline_monotonic = time.monotonic() + 50000.0
    state.flow_timeout_effective_seconds = 120
    set_cancellation_token(None)
    await check_cancellation(state)


@pytest.mark.asyncio
async def test_check_cancellation_wall_clock_before_redis_cancel(
    app, container, make_test_state, unique_id: str
) -> None:
    """Сначала дедлайн, затем Redis: при просроченном дедлайне — FlowWallClockTimeoutError."""
    state = make_test_state(
        task_id=f"task-{unique_id}",
        context_id=f"ctx-{unique_id}",
        session_id=f"flow_w_{unique_id}:ctx-{unique_id}",
    )
    state.flow_deadline_monotonic = time.monotonic() - 0.5
    state.flow_timeout_effective_seconds = 30
    token = CancellationToken(f"task-{unique_id}", container.redis_client)
    set_cancellation_token(token)
    try:
        await token.cancel()
        with pytest.raises(FlowWallClockTimeoutError):
            await check_cancellation(state)
    finally:
        await token.cleanup()
        set_cancellation_token(None)


@pytest.mark.asyncio
async def test_check_cancellation_redis_cancel_when_deadline_not_set(
    app, container, make_test_state, unique_id: str
) -> None:
    state = make_test_state(
        task_id=f"task-{unique_id}",
        context_id=f"ctx-{unique_id}",
        session_id=f"flow_r_{unique_id}:ctx-{unique_id}",
    )
    state.flow_deadline_monotonic = None
    state.flow_timeout_effective_seconds = None
    token = CancellationToken(f"task-{unique_id}", container.redis_client)
    set_cancellation_token(token)
    try:
        await token.cancel()
        with pytest.raises(FlowCancelled) as exc_info:
            await check_cancellation(state)
        assert exc_info.value.task_id == f"task-{unique_id}"
    finally:
        await token.cleanup()
        set_cancellation_token(None)


@pytest.mark.asyncio
async def test_code_node_node_timeout_stops_overlong_await(
    app, make_test_state, unique_id: str
) -> None:
    code = "\nimport asyncio\nasync def run(args, state):\n    await asyncio.sleep(30)\n    return state\n"
    node = CodeNode(
        f"sleep_node_{unique_id}", config={"type": "code", "code": code, "node_timeout_seconds": 1}
    )
    state = make_test_state(
        task_id=f"task-{unique_id}",
        context_id=f"ctx-{unique_id}",
        session_id=f"flow_n_{unique_id}:ctx-{unique_id}",
    )
    with pytest.raises(NodeWallClockTimeoutError) as exc_info:
        await node.run(state)
    assert exc_info.value.code == "NODE_WALL_CLOCK_TIMEOUT"
    assert exc_info.value.payload["node_id"] == f"sleep_node_{unique_id}"
    assert exc_info.value.payload["timeout_seconds"] == 1


@pytest.mark.asyncio
async def test_flow_run_aborts_on_expired_deadline_before_node(
    app, make_test_state, unique_id: str
) -> None:
    code = '\nasync def run(args, state):\n    state.proof = "must_not_run"\n    return state\n'
    n_id = f"step1_{unique_id}"
    node = CodeNode(n_id, config={"type": "code", "code": code})
    flow = Flow(
        flow_id=f"linear_{unique_id}",
        name="linear",
        entry=n_id,
        nodes={n_id: node},
        edges=[{"from_node": n_id, "to_node": None}],
    )
    state = make_test_state(
        task_id=f"task-{unique_id}",
        context_id=f"ctx-{unique_id}",
        user_id=f"user-{unique_id}",
        session_id=f"flow_f_{unique_id}:ctx-{unique_id}",
    )
    state.flow_deadline_monotonic = time.monotonic() - 0.01
    state.flow_timeout_effective_seconds = 5
    with pytest.raises(FlowWallClockTimeoutError):
        await flow.run(state)
    assert getattr(state, "proof", None) is None


@pytest.mark.asyncio
async def test_apply_flow_wall_clock_deadline_clamps_to_settings_cap(
    app, make_test_state, unique_id: str
) -> None:
    state = make_test_state(
        task_id=f"task-{unique_id}",
        context_id=f"ctx-{unique_id}",
        session_id=f"flow_clamp_{unique_id}:ctx-{unique_id}",
    )
    cap = get_flow_execution_wall_time_cap_seconds()
    apply_flow_wall_clock_deadline(state, 9999999)
    assert state.flow_timeout_effective_seconds == cap
    assert state.flow_deadline_monotonic is not None
    assert state.flow_deadline_monotonic <= time.monotonic() + float(cap) + 1.0


def test_flow_config_rejects_timeout_above_service_cap(app, unique_id: str) -> None:
    cap = get_flow_execution_wall_time_cap_seconds()
    with pytest.raises(ValueError, match="timeout: максимум"):
        FlowConfig(
            flow_id=f"fx_{unique_id}",
            name="n",
            type=FlowType.LOCAL,
            entry="a",
            nodes={"a": {"type": "code", "code": "async def run(s):\n    return s", "name": "a"}},
            edges=[{"from_node": "a", "to_node": None}],
            timeout=cap + 1,
        )


def test_node_config_rejects_node_timeout_above_service_cap(app, unique_id: str) -> None:
    from apps.flows.src.models.enums import NodeType

    cap = get_node_execution_wall_time_cap_seconds()
    with pytest.raises(ValueError, match="node_timeout_seconds: максимум"):
        NodeConfig(
            node_id=f"n_{unique_id}", type=NodeType.CODE, name="x", node_timeout_seconds=cap + 1
        )


def test_node_config_rejects_max_visits_above_graph_cap(app, unique_id: str) -> None:
    from apps.flows.src.models.enums import NodeType

    cap = get_graph_max_iterations()
    with pytest.raises(ValueError, match="max_visits_per_run"):
        NodeConfig(
            node_id=f"n_mv_{unique_id}",
            type=NodeType.CODE,
            name="x",
            code="async def run(s):\n    return s",
            max_visits_per_run=cap + 1,
        )


@pytest.mark.asyncio
async def test_http_validate_requires_python_entrypoint(client, app, unique_id: str) -> None:
    r = await client.post(
        "/flows/api/v1/code/validate", json={"code": "while True:\n    pass\n", "node_type": "code"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    err = (body.get("error") or "").lower()
    assert "функция" in err or "function" in err


@pytest.mark.asyncio
async def test_http_execute_node_timeout_surfaces_error(client, app, unique_id: str) -> None:
    code = "async def run(args, state):\n    while True:\n        pass\n"
    r = await client.post(
        "/flows/api/v1/code/execute",
        json={
            "node_type": "code",
            "node_config": {"type": "code", "code": code, "node_timeout_seconds": 1},
            "state": {
                "task_id": f"t_{unique_id}",
                "context_id": f"c_{unique_id}",
                "session_id": f"ex_{unique_id}:c_{unique_id}",
            },
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is False
    err = data.get("error") or ""
    assert "NODE_WALL_CLOCK_TIMEOUT" in err or "превышен" in err.lower() or "лимит" in err.lower()


def test_default_flow_timeout_must_not_exceed_cap_in_valid_settings() -> None:
    s = get_settings()
    assert s.default_flow_timeout_seconds <= s.flow_execution_wall_time_cap_seconds
