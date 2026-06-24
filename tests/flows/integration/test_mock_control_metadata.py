"""
Интеграционные тесты Mock Control System через metadata.__mock__.

Проверяют реальный runtime-путь (не глобальный TESTING MockLLM):
- per-node LLM очередь: разные llm-ноды получают разные ответы;
- список ответов на сущность (FIFO), в т.ч. несколько ответов в одной ноде;
- mock tool результата;
- fail-closed, когда llm-нода не замокана.

permission_groups берём admin/developers — те же, что у flow example_react,
поэтому системный клиент проходит и permission flow, и permission mock.
"""

import asyncio
import json
import uuid

import pytest
from httpx import AsyncClient

_MOCK_GROUPS = ["admin", "developers"]


def make_message(text: str) -> dict[str, object]:
    return {
        "messageId": str(uuid.uuid4()),
        "role": "user",
        "parts": [{"kind": "text", "text": text}],
    }


def result_text(result: dict[str, object]) -> str:
    """Склеивает весь текст из artifacts + history результата A2A."""
    return json.dumps(result, ensure_ascii=False)


async def send_sync(
    client: AsyncClient,
    flow_id: str,
    *,
    unique_id: str,
    text: str,
    branch: str,
    mock: dict[str, object],
) -> dict[str, object]:
    metadata: dict[str, object] = {"branch": branch}
    metadata["__mock__"] = {
        "enabled": True,
        "permission_groups": _MOCK_GROUPS,
        **mock,
    }
    response = await client.post(
        f"/flows/api/v1/{flow_id}",
        json={
            "jsonrpc": "2.0",
            "id": f"test-{unique_id}",
            "method": "message/send",
            "params": {
                "message": {**make_message(text), "contextId": f"ctx-{unique_id}"},
                "metadata": metadata,
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "result" in body, body
    return body["result"]


class TestPerNodeLlmMock:
    """Разные llm-ноды получают разные списки ответов."""

    @pytest.mark.asyncio
    async def test_order_node_uses_its_own_mock(self, client: AsyncClient, unique_id: str):
        answer = f"ORDER_MOCK_{unique_id}"
        result = await send_sync(
            client,
            "example_graph",
            unique_id=unique_id,
            text="заказ 1042: статус",
            branch="fast_track",
            mock={"nodes": {"order_processor": [{"type": "text", "content": answer}]}},
        )
        assert answer in result_text(result)

    @pytest.mark.asyncio
    async def test_two_routes_get_distinct_answers(self, client: AsyncClient, unique_id: str):
        order_answer = f"ORDER_{unique_id}"
        complaint_answer = f"COMPLAINT_{unique_id}"

        order_result = await send_sync(
            client,
            "example_graph",
            unique_id=f"{unique_id}-o",
            text="заказ 99: где он",
            branch="fast_track",
            mock={"nodes": {"order_processor": [{"type": "text", "content": order_answer}]}},
        )
        complaint_result = await send_sync(
            client,
            "example_graph",
            unique_id=f"{unique_id}-c",
            text="жалоба на доставку",
            branch="orders_only",
            mock={
                "nodes": {
                    "complaint_processor": [{"type": "text", "content": complaint_answer}]
                }
            },
        )

        assert order_answer in result_text(order_result)
        assert complaint_answer not in result_text(order_result)
        assert complaint_answer in result_text(complaint_result)
        assert order_answer not in result_text(complaint_result)


class TestEntityResponseList:
    """Список ответов на сущность: несколько ответов в одной llm-ноде + mock tool."""

    @pytest.mark.asyncio
    async def test_node_list_tool_call_then_text(self, client: AsyncClient, unique_id: str):
        flow_id = f"mock_tool_flow_{unique_id}"
        create = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Mock tool flow",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "Use calculator then answer",
                        "tools": ["calculator"],
                        "llm": {"provider": "humanitec_llm", "model": "auto"},
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
            },
        )
        assert create.status_code == 200, create.text
        try:
            final_answer = f"FINAL_{unique_id}"
            result = await send_sync(
                client,
                flow_id,
                unique_id=unique_id,
                text="2+2",
                branch="default",
                mock={
                    "nodes": {
                        "main": [
                            {
                                "type": "tool_call",
                                "tool": "calculator",
                                "args": {"expression": "2+2"},
                            },
                            {"type": "text", "content": final_answer},
                        ]
                    },
                    "tools": {"calculator": [{"type": "result", "content": "MOCK_TOOL_4"}]},
                },
            )
            assert final_answer in result_text(result)
            assert "MOCK_TOOL_4" in result_text(result)
        finally:
            await client.delete(f"/flows/api/v1/flows/{flow_id}")


class TestStreaming:
    """metadata.__mock__ работает и со streaming (message/stream)."""

    @pytest.mark.asyncio
    async def test_node_mock_streaming(self, client: AsyncClient, unique_id: str):
        answer = f"STREAM_MOCK_{unique_id}"
        async with client.stream(
            "POST",
            "/flows/api/v1/example_graph",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/stream",
                "params": {
                    "message": {
                        **make_message("заказ 3: статус"),
                        "contextId": f"ctx-{unique_id}",
                    },
                    "metadata": {
                        "branch": "fast_track",
                        "__mock__": {
                            "enabled": True,
                            "permission_groups": _MOCK_GROUPS,
                            "nodes": {
                                "order_processor": [{"type": "text", "content": answer}]
                            },
                        },
                    },
                },
            },
        ) as response:
            assert response.status_code == 200
            events = [line async for line in response.aiter_lines() if line.startswith("data:")]
            assert events
            assert any(answer in line for line in events)


class TestFailClosed:
    """Mock включён, но llm-нода не замокана и нет общей очереди — задача падает."""

    @pytest.mark.asyncio
    async def test_unmocked_llm_node_fails(self, client: AsyncClient, unique_id: str):
        result = await send_sync(
            client,
            "example_graph",
            unique_id=unique_id,
            text="заказ 5: статус",
            branch="fast_track",
            # Мокаем не ту ноду, что реально исполняется (order_processor), без общей llm.
            mock={"nodes": {"complaint_processor": [{"type": "text", "content": "nope"}]}},
        )
        state = result.get("status", {})
        assert state.get("state") != "completed", result_text(result)


class TestRealTaskiqWorkerPath:
    """metadata.__mock__ применяется в worker при async-исполнении."""

    @pytest.mark.real_taskiq
    @pytest.mark.asyncio
    async def test_async_worker_applies_node_mock(self, client: AsyncClient, unique_id: str):
        answer = f"ASYNC_MOCK_{unique_id}"
        context_id = f"ctx-{unique_id}"
        task_id = f"task-{unique_id}"
        submit = await client.post(
            "/flows/api/v1/example_graph",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {
                    "message": {
                        **make_message("заказ 7: где"),
                        "contextId": context_id,
                        "taskId": task_id,
                    },
                    "metadata": {
                        "branch": "fast_track",
                        "execution_mode": "async",
                        "__mock__": {
                            "enabled": True,
                            "permission_groups": _MOCK_GROUPS,
                            "nodes": {
                                "order_processor": [{"type": "text", "content": answer}]
                            },
                        },
                    },
                },
            },
        )
        assert submit.status_code == 200, submit.text
        submitted_id = submit.json()["result"]["id"]

        final_state = None
        for _ in range(120):
            poll = await client.post(
                "/flows/api/v1/example_graph",
                json={
                    "jsonrpc": "2.0",
                    "id": f"poll-{unique_id}",
                    "method": "tasks/get",
                    "params": {"id": submitted_id},
                },
            )
            assert poll.status_code == 200, poll.text
            state = poll.json()["result"]["status"]["state"]
            if state in ("completed", "input-required", "failed", "canceled", "rejected"):
                final_state = state
                assert answer in result_text(poll.json()["result"])
                break
            await asyncio.sleep(0.5)
        assert final_state == "completed"
