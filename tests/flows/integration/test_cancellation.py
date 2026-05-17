"""
Интеграционные тесты отмены выполнения flow (FlowCancelled).

Проверяют:
1. Отмена между нодами графа (code nodes).
2. Отмена между итерациями ReAct (LLM flow).
3. State не сохраняется после отмены (восстановление).

Без моков (кроме MockLLM). Реальные PostgreSQL, Redis, FlowFactory.
"""

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.models import Edge, FlowConfig
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.state.cancellation import (
    CancellationToken,
    FlowCancelled,
    set_cancellation_token,
)
from core.state import ExecutionState


class TestCancellationBetweenNodes:
    """Отмена между нодами графа (code nodes)."""

    @pytest.mark.asyncio
    async def test_cancel_before_first_node(self, app, unique_id):
        """
        Cancel-ключ установлен ДО запуска flow.
        _execute_loop видит cancel на первой же итерации -> FlowCancelled.
        Ни одна нода не выполняется.
        """
        container = get_container()

        flow = await Flow.from_config(
            config={
                "id": f"cancel_graph_{unique_id}",
                "name": "Cancel Graph",
                "entry": "node_a",
                "nodes": {
                    "node_a": {
                        "type": "code",
                        "code": (
                            "async def run(args, state):\n"
                            "    state['executed_a'] = True\n"
                            "    return state\n"
                        ),
                    },
                    "node_b": {
                        "type": "code",
                        "code": (
                            "async def run(args, state):\n"
                            "    state['executed_b'] = True\n"
                            "    return state\n"
                        ),
                    },
                },
                "edges": [
                    {"from": "node_a", "to": "node_b"},
                    {"from": "node_b", "to": None},
                ],
            },
            variables={},
            container=container,
        )

        state = ExecutionState(
            task_id=f"task-{unique_id}",
            context_id=f"ctx-{unique_id}",
            user_id=f"user-{unique_id}",
            session_id=f"cancel_graph_{unique_id}:ctx-{unique_id}",
            content="go",
        )

        token = CancellationToken(
            state.task_id,
            container.redis_client,
            check_interval=0,
        )
        await token.cancel()
        set_cancellation_token(token)

        try:
            with pytest.raises(FlowCancelled) as exc_info:
                await flow.run(state)

            assert exc_info.value.task_id == state.task_id
            assert not getattr(state, "executed_a", False)
            assert not getattr(state, "executed_b", False)
        finally:
            await token.cleanup()
            set_cancellation_token(None)

    @pytest.mark.asyncio
    async def test_cancel_between_two_nodes(self, app, unique_id):
        """
        Cancel-ключ устанавливается по ходу выполнения первой ноды.
        Первая нода выполняется, вторая — нет.
        """
        container = get_container()
        task_id = f"task-{unique_id}"

        flow = await Flow.from_config(
            config={
                "id": f"cancel_mid_{unique_id}",
                "name": "Cancel Mid",
                "entry": "node_a",
                "nodes": {
                    "node_a": {
                        "type": "code",
                        "code": (
                            "async def run(args, state):\n"
                            "    state['executed_a'] = True\n"
                            "    return state\n"
                        ),
                    },
                    "node_b": {
                        "type": "code",
                        "code": (
                            "async def run(args, state):\n"
                            "    state['executed_b'] = True\n"
                            "    return state\n"
                        ),
                    },
                },
                "edges": [
                    {"from": "node_a", "to": "node_b"},
                    {"from": "node_b", "to": None},
                ],
            },
            variables={},
            container=container,
        )

        state = ExecutionState(
            task_id=task_id,
            context_id=f"ctx-{unique_id}",
            user_id=f"user-{unique_id}",
            session_id=f"cancel_mid_{unique_id}:ctx-{unique_id}",
            content="go",
        )

        token = CancellationToken(
            task_id,
            container.redis_client,
            check_interval=0,
        )
        set_cancellation_token(token)

        node_a = flow.nodes["node_a"]
        original_execute = node_a.execute

        async def patched_execute(run_state):
            result = await original_execute(run_state)
            await token.cancel()
            return result

        node_a.execute = patched_execute

        try:
            with pytest.raises(FlowCancelled):
                await flow.run(state)

            assert getattr(state, "executed_a", False) is True
            assert not getattr(state, "executed_b", False)
        finally:
            await token.cleanup()
            set_cancellation_token(None)


class _DelayedCancelToken(CancellationToken):
    """
    Тестовый токен: возвращает cancelled=True только после skip_first проверок.
    Имитирует ситуацию когда cancel появляется МЕЖДУ итерациями ReAct.
    """

    def __init__(self, task_id: str, redis_client: object, skip_first: int = 1):
        super().__init__(task_id, redis_client, check_interval=0)
        self._checks_remaining = skip_first

    async def is_cancelled(self) -> bool:
        if self._checks_remaining > 0:
            self._checks_remaining -= 1
            return False
        return True


class TestCancellationInReactLoop:
    """Отмена между итерациями ReAct (LLM flow)."""

    @pytest.mark.asyncio
    async def test_cancel_during_react_loop(self, app, mock_llm_with_queue, unique_id):
        """
        MockLLM возвращает tool_call на первой итерации.
        _DelayedCancelToken пропускает первые проверки cancel (итерация 1),
        а на второй итерации _react_loop -> FlowCancelled.
        Второй ответ MockLLM не используется.
        """
        container = get_container()
        task_id = f"task-{unique_id}"

        flow = await Flow.from_config(
            config={
                "id": f"cancel_react_{unique_id}",
                "name": "Cancel React",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "You are an assistant.",
                        "tools": [
                            {
                                "tool_id": "dummy",
                                "type": "code",
                                "name": "dummy",
                                "description": "dummy tool",
                                "code": (
                                    "async def run(args, state):\n"
                                    "    return 'ok'\n"
                                ),
                            },
                        ],
                    },
                },
                "edges": [
                    {"from": "main", "to": None},
                ],
            },
            variables={},
            container=container,
        )

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "dummy", "args": {}},
            "This should not be reached",
        ])

        state = ExecutionState(
            task_id=task_id,
            context_id=f"ctx-{unique_id}",
            user_id=f"user-{unique_id}",
            session_id=f"cancel_react_{unique_id}:ctx-{unique_id}",
            content="go",
        )

        # skip_first=1: первая проверка check_cancellation (начало итерации 1) — пропуск,
        # все последующие — cancelled. На итерации 2 -> FlowCancelled.
        token = _DelayedCancelToken(task_id, container.redis_client, skip_first=1)
        set_cancellation_token(token)

        try:
            with pytest.raises(FlowCancelled):
                await flow.run(state)

            assert state.response != "This should not be reached"
        finally:
            set_cancellation_token(None)


class TestCancellationStateRestoration:
    """State не сохраняется после отмены (process_task)."""

    @pytest.mark.asyncio
    async def test_state_not_saved_after_cancel(
        self, app, mock_llm_with_queue, unique_id
    ):
        """
        1. Первый запрос выполняется нормально -> state сохраняется.
        2. Второй запрос отменяется -> state НЕ должен измениться.
        3. Проверяем что state в БД совпадает с результатом первого запроса.
        """
        container = get_container()
        flow_id = f"cancel_state_{unique_id}"
        context_id = f"ctx-{unique_id}"
        session_id = f"{flow_id}:{context_id}"

        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Cancel State Test",
            entry="main",
            nodes={
                "main": {
                    "type": "code",
                    "code": (
                        "async def run(args, state):\n"
                        "    counter = state.get('counter', 0)\n"
                        "    state['counter'] = counter + 1\n"
                        "    state['response'] = f'counter={counter + 1}'\n"
                        "    return state\n"
                    ),
                },
            },
            edges=[Edge(from_node="main", to_node=None)],
        )
        await container.flow_repository.set(flow_config)

        flow = await container.flow_factory.get_flow(flow_id)

        state_v1 = ExecutionState(
            task_id=f"task1-{unique_id}",
            context_id=context_id,
            user_id=f"user-{unique_id}",
            session_id=session_id,
            content="first",
        )
        result_v1 = await flow.run(state_v1)
        assert result_v1.response == "counter=1"

        await container.state_manager.save_state(session_id, result_v1)

        saved_before_cancel = await container.state_manager.get_state(session_id)
        assert saved_before_cancel is not None
        assert saved_before_cancel.response == "counter=1"

        state_v2 = ExecutionState(
            task_id=f"task2-{unique_id}",
            context_id=context_id,
            user_id=f"user-{unique_id}",
            session_id=session_id,
            content="second",
        )

        token = CancellationToken(
            state_v2.task_id,
            container.redis_client,
            check_interval=0,
        )
        await token.cancel()
        set_cancellation_token(token)

        flow_v2 = await container.flow_factory.get_flow(flow_id)

        try:
            with pytest.raises(FlowCancelled):
                await flow_v2.run(state_v2)
        finally:
            await token.cleanup()
            set_cancellation_token(None)

        saved_after_cancel = await container.state_manager.get_state(session_id)
        assert saved_after_cancel is not None
        assert saved_after_cancel.response == "counter=1"
        assert saved_after_cancel.get("counter") == 1
