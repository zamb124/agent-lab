"""Pending-call подсистема: submit → pending-ряд → push webhook → continuation.

Тесты на реальной БД и реальном HTTP (ephemeral A2A-сервер, ASGI-приложение
с настоящим роутером `a2a_push_router`). Кейсы: отправка SendMessage с
returnImmediately + taskPushNotificationConfig, ACK не-терминальных кадров,
атомарный consume терминала, идемпотентный повтор webhook'а, неверный токен,
deadline-sweep с потерянным webhook'ом и dedup resume-результат.
"""

import hashlib
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import cast

import pytest
from aiohttp import web
from fastapi import FastAPI, Request, Response
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import RequestResponseEndpoint

from apps.idle.tasks.a2a_pending_tasks import (
    a2a_call_finished,
    a2a_pending_sweep_tick,
)
from apps.idle.tasks.task_names import TASK_A2A_CALL_FINISHED
from core.a2a.pending_call import (
    A2A_STATE_DEADLINE_EXCEEDED,
    PlatformA2APendingCall,
)
from core.a2a.push_callback import hash_callback_token
from core.a2a.submit import a2a_task_outcome, submit_a2a_call
from core.api.a2a_push import a2a_push_router
from core.clients.a2a_client import A2AClient
from core.logging.context import bind_log_context, clear_log_context
from core.types import JsonObject, require_json_object
from tests.fixtures.aiohttp_ephemeral import ephemeral_web_server


def _task_scope() -> None:
    """Request scope worker'а: LoggingMiddleware биндит request_id/trace_id."""
    bind_log_context(request_id="a2a-task-req", trace_id="a2a-task-trace")


@pytest.fixture
async def push_app() -> AsyncIterator[AsyncClient]:
    """Реальное ASGI-приложение с каноничным push-роутером.

    Middleware воспроизводит request scope продакшна: request_id/trace_id
    в лог-контексте, как делает HTTP-middleware сервиса — иначе enqueue
    continuation справедливо требует background_kind.
    """
    app = FastAPI()

    @app.middleware("http")
    async def request_scope(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        _ = request
        bind_log_context(request_id="push-test-req", trace_id="push-test-trace")
        try:
            return await call_next(request)
        finally:
            clear_log_context()

    app.include_router(a2a_push_router, prefix="/x")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://push"
    ) as client:
        yield client


@pytest.fixture
async def submitted_agent() -> AsyncIterator[JsonObject]:
    """A2A-агент: принимает SendMessage, отвечает SUBMITTED, логирует запросы."""
    public: JsonObject = {"base": "http://127.0.0.1:0"}
    received: list[JsonObject] = []

    async def handle_rpc(request: web.Request) -> web.Response:
        data = cast(JsonObject, await request.json())
        received.append(data)
        message = require_json_object(
            require_json_object(data["params"], "a2a.params")["message"],
            "a2a.message",
        )
        return web.json_response(
            {
                "jsonrpc": "2.0",
                "id": data["id"],
                "result": {
                    "id": message["taskId"],
                    "contextId": message["contextId"],
                    "status": {"state": "TASK_STATE_SUBMITTED"},
                    "artifacts": [],
                },
            }
        )

    app = web.Application()
    _ = app.router.add_post("/", handle_rpc)
    async with ephemeral_web_server(app) as base_url:
        public["base"] = base_url
        yield {"url": base_url, "received": received}


async def _register_pending(
    a2a_task_id: str,
    *,
    token_hint: str = "tok",
    deadline: datetime | None = None,
    dedup_key: str | None = None,
    base_url: str = "http://agent.test",
) -> PlatformA2APendingCall:
    return await PlatformA2APendingCall.register(
        a2a_task_id=a2a_task_id,
        service="flows",
        company_id="system",
        user_id="test_user",
        base_url=base_url,
        continuation_task=TASK_A2A_CALL_FINISHED.name,
        continuation_kwargs={"marker": "k"},
        callback_token_hash=hash_callback_token(token_hint),
        deadline_at=deadline
        or datetime.now(timezone.utc) + timedelta(seconds=60),
        dedup_key=dedup_key,
    )


def _push_body(task_id: str, state: str) -> JsonObject:
    return {
        "statusUpdate": {
            "taskId": task_id,
            "status": {"state": state},
            "final": True,
        }
    }


def _fired_count(result: JsonObject) -> int:
    calls = result["calls"]
    assert isinstance(calls, dict)
    fired = calls["fired"]
    assert isinstance(fired, int)
    return fired


class TestSubmitA2ACall:
    async def test_submit_registers_pending_and_sends_push_config(
        self, submitted_agent: JsonObject, unique_id: str
    ) -> None:
        """SendMessage уходит с returnImmediately + push config, ряд — pending."""
        base_url = submitted_agent["url"]
        assert isinstance(base_url, str)
        received = submitted_agent["received"]
        assert isinstance(received, list)
        row = await submit_a2a_call(
            a2a_client=A2AClient(),
            service="flows",
            company_id="system",
            user_id="test_user",
            base_url=base_url,
            content="hello",
            context_id=f"ctx-{unique_id}",
            a2a_task_id=f"task-{unique_id}",
            continuation=TASK_A2A_CALL_FINISHED,
            continuation_kwargs={"marker": "v"},
            deadline_seconds=300.0,
            dedup_key=f"dedup-{unique_id}",
        )

        assert row.a2a_task_id == f"task-{unique_id}"
        assert row.status == "pending"
        assert row.continuation_task == TASK_A2A_CALL_FINISHED.name
        assert row.dedup_key == f"dedup-{unique_id}"

        assert len(received) == 1
        request = received[0]
        assert isinstance(request, dict)
        assert request["method"] == "SendMessage"
        params = request["params"]
        assert isinstance(params, dict)
        configuration = params["configuration"]
        assert isinstance(configuration, dict)
        assert configuration["returnImmediately"] is True
        push_config = configuration["taskPushNotificationConfig"]
        assert isinstance(push_config, dict)
        push_url = push_config["url"]
        assert isinstance(push_url, str)
        assert push_url.endswith("/flows/api/v1/internal/a2a/push")
        # Токен по проводу совпадает с хешем в базе.
        stored = await PlatformA2APendingCall.pending_by_id(row.a2a_task_id)
        assert stored is not None
        token = push_config["token"]
        assert isinstance(token, str)
        assert stored.callback_token_hash == hash_callback_token(token)

    async def test_submit_relinks_remote_task_id(self, unique_id: str) -> None:
        """Remote вернул другой taskId — pending-ряд перелинкован на него."""

        async def handle_rpc(request: web.Request) -> web.Response:
            data = cast(JsonObject, await request.json())
            message = require_json_object(
                require_json_object(data["params"], "a2a.params")["message"],
                "a2a.message",
            )
            return web.json_response(
                {
                    "jsonrpc": "2.0",
                    "id": data["id"],
                    "result": {
                        "id": f"remote-{unique_id}",
                        "contextId": message["contextId"],
                        "status": {"state": "TASK_STATE_SUBMITTED"},
                        "artifacts": [],
                    },
                }
            )

        app = web.Application()
        _ = app.router.add_post("/", handle_rpc)
        async with ephemeral_web_server(app) as base_url:
            row = await submit_a2a_call(
                a2a_client=A2AClient(),
                service="flows",
                company_id="system",
                user_id="test_user",
                base_url=base_url,
                content="hello",
                a2a_task_id=f"client-{unique_id}",
                continuation=TASK_A2A_CALL_FINISHED,
                continuation_kwargs={},
                deadline_seconds=300.0,
            )
        assert row.a2a_task_id == f"remote-{unique_id}"
        assert (
            await PlatformA2APendingCall.pending_by_id(f"client-{unique_id}")
            is None
        )


class TestPushEndpoint:
    async def test_open_state_acks_without_consume(
        self, push_app: AsyncClient, unique_id: str
    ) -> None:
        """submitted/working кадр — чистый 200, ряд остаётся pending."""
        row = await _register_pending(
            f"push-open-{unique_id}", token_hint="t1"
        )
        response = await push_app.post(
            "/x/internal/a2a/push",
            json=_push_body(row.a2a_task_id, "TASK_STATE_WORKING"),
            headers={"Authorization": "Bearer t1"},
        )
        assert response.status_code == 200
        after = await PlatformA2APendingCall.pending_by_id(row.a2a_task_id)
        assert after is not None and after.status == "pending"

    async def test_terminal_consumes_and_enqueues(
        self, push_app: AsyncClient, unique_id: str
    ) -> None:
        """Терминал: consume + continuation enqueue + 200."""
        row = await _register_pending(
            f"push-term-{unique_id}", token_hint="t2"
        )
        response = await push_app.post(
            "/x/internal/a2a/push",
            json=_push_body(row.a2a_task_id, "TASK_STATE_COMPLETED"),
            headers={"Authorization": "Bearer t2"},
        )
        assert response.status_code == 200
        after = await PlatformA2APendingCall.pending_by_id(row.a2a_task_id)
        assert after is not None and after.status == "consumed"

    async def test_duplicate_terminal_is_idempotent_ack(
        self, push_app: AsyncClient, unique_id: str
    ) -> None:
        """Повторная доставка терминала — 200, без второго consume."""
        row = await _register_pending(
            f"push-dup-{unique_id}", token_hint="t3"
        )
        headers = {"Authorization": "Bearer t3"}
        first = await push_app.post(
            "/x/internal/a2a/push",
            json=_push_body(row.a2a_task_id, "TASK_STATE_FAILED"),
            headers=headers,
        )
        second = await push_app.post(
            "/x/internal/a2a/push",
            json=_push_body(row.a2a_task_id, "TASK_STATE_FAILED"),
            headers=headers,
        )
        assert first.status_code == 200
        assert second.status_code == 200

    async def test_wrong_token_forbidden(
        self, push_app: AsyncClient, unique_id: str
    ) -> None:
        row = await _register_pending(
            f"push-auth-{unique_id}", token_hint="t4"
        )
        response = await push_app.post(
            "/x/internal/a2a/push",
            json=_push_body(row.a2a_task_id, "TASK_STATE_COMPLETED"),
            headers={"Authorization": "Bearer wrong"},
        )
        assert response.status_code == 403
        after = await PlatformA2APendingCall.pending_by_id(row.a2a_task_id)
        assert after is not None and after.status == "pending"

    async def test_missing_token_unauthorized(
        self, push_app: AsyncClient
    ) -> None:
        response = await push_app.post(
            "/x/internal/a2a/push",
            json=_push_body("x", "TASK_STATE_COMPLETED"),
        )
        assert response.status_code == 401

    async def test_unknown_task_404(self, push_app: AsyncClient) -> None:
        response = await push_app.post(
            "/x/internal/a2a/push",
            json=_push_body("no-such-task", "TASK_STATE_COMPLETED"),
            headers={"Authorization": "Bearer t"},
        )
        assert response.status_code == 404

    async def test_body_without_task_id_400(
        self, push_app: AsyncClient
    ) -> None:
        response = await push_app.post(
            "/x/internal/a2a/push",
            json={
                "statusUpdate": {
                    "status": {"state": "TASK_STATE_COMPLETED"}
                }
            },
            headers={"Authorization": "Bearer t"},
        )
        assert response.status_code == 400


class TestCallFinishedContinuation:
    async def test_full_task_payload_stores_result_and_resumes(
        self, unique_id: str
    ) -> None:
        """Полный Task в payload — outcome пишется в ряд, resume ставится."""
        row = await _register_pending(
            f"fin-{unique_id}",
            dedup_key=f"dedup-fin-{unique_id}",
        )
        _ = await PlatformA2APendingCall.consume(row.a2a_task_id)
        task_payload: JsonObject = {
            "id": row.a2a_task_id,
            "status": {"state": "TASK_STATE_COMPLETED"},
            "artifacts": [
                {
                    "artifactId": "a1",
                    "name": "response",
                    "parts": [{"text": "done-text"}],
                }
            ],
        }
        _task_scope()
        try:
            result = await a2a_call_finished(
                a2a_task_id=row.a2a_task_id,
                a2a_state="completed",
                a2a_payload={"task": task_payload},
                a2a_base_url=row.base_url,
                resume_task=TASK_A2A_CALL_FINISHED.name,
                resume_kwargs={"again": "yes"},
            )
        finally:
            clear_log_context()
        assert result["stored"] is True
        assert result["resumed"] is True
        after = await PlatformA2APendingCall.pending_by_id(row.a2a_task_id)
        assert after is not None
        assert after.result_payload is not None
        assert after.result_payload["status"] == "completed"

    async def test_deadline_exceeded_records_failed_outcome(
        self, unique_id: str
    ) -> None:
        row = await _register_pending(f"fin-dl-{unique_id}")
        _ = await PlatformA2APendingCall.consume(row.a2a_task_id)
        _task_scope()
        try:
            result = await a2a_call_finished(
                a2a_task_id=row.a2a_task_id,
                a2a_state=A2A_STATE_DEADLINE_EXCEEDED,
                a2a_payload={},
                a2a_base_url=row.base_url,
            )
        finally:
            clear_log_context()
        assert result["stored"] is True
        assert result["resumed"] is False
        after = await PlatformA2APendingCall.pending_by_id(row.a2a_task_id)
        assert after is not None
        assert after.result_payload is not None
        assert after.result_payload["status"] == "failed"
        assert "deadline" in str(after.result_payload["error"]).lower()

    async def test_missing_row_is_noop(self, unique_id: str) -> None:
        _task_scope()
        try:
            result = await a2a_call_finished(
                a2a_task_id=f"missing-{unique_id}",
                a2a_state="completed",
                a2a_payload={},
                a2a_base_url="http://x",
            )
        finally:
            clear_log_context()
        assert result["stored"] is False


class TestDedupResume:
    async def test_latest_by_dedup_key_created_at_desc_and_take_result(
        self, unique_id: str
    ) -> None:
        """Повторный прогон вызывающего кода забирает payload по dedup_key."""
        dedup_key = f"dedup-take-{unique_id}"
        row = await _register_pending(f"take-{unique_id}", dedup_key=dedup_key)
        _ = await PlatformA2APendingCall.store_result(
            row.a2a_task_id, {"status": "completed", "response": "ok"}
        )
        found = await PlatformA2APendingCall.latest_by_dedup_key_created_at_desc("flows", dedup_key)
        assert found is not None
        taken = await PlatformA2APendingCall.take_result("flows", dedup_key)
        assert taken is not None
        assert taken["response"] == "ok"
        # Забор одноразовый: resolved → consumed, повтор — None.
        again = await PlatformA2APendingCall.take_result("flows", dedup_key)
        assert again is None


class TestSweeper:
    async def test_expired_pending_fires_deadline_continuation(
        self, unique_id: str
    ) -> None:
        """Просроченный ряд: remote недоступен → deadline_exceeded continuation."""
        _ = await _register_pending(
            f"sweep-{unique_id}",
            deadline=datetime.now(timezone.utc) - timedelta(seconds=1),
            base_url="http://127.0.0.1:1",
        )
        _task_scope()
        try:
            result = await a2a_pending_sweep_tick()
        finally:
            clear_log_context()
        assert _fired_count(result) >= 1
        after = await PlatformA2APendingCall.pending_by_id(
            f"sweep-{unique_id}"
        )
        assert after is not None and after.status == "expired"

    async def test_lost_webhook_sweep_uses_real_terminal(
        self, unique_id: str
    ) -> None:
        """Remote уже в терминале (webhook потерян) — sweep шлёт реальный state."""

        async def handle_rpc(request: web.Request) -> web.Response:
            data = cast(JsonObject, await request.json())
            if data["method"] == "GetTask":
                params = require_json_object(data["params"], "a2a.params")
                return web.json_response(
                    {
                        "jsonrpc": "2.0",
                        "id": data["id"],
                        "result": {
                            "id": params["id"],
                            "status": {
                                "state": "TASK_STATE_COMPLETED",
                                "message": {
                                    "role": "ROLE_AGENT",
                                    "parts": [{"text": "swept"}],
                                },
                            },
                            "artifacts": [],
                        },
                    }
                )
            return web.json_response(
                {"jsonrpc": "2.0", "id": data["id"], "error": {"code": -32601}}
            )

        app = web.Application()
        _ = app.router.add_post("/", handle_rpc)
        async with ephemeral_web_server(app) as base_url:
            _ = await _register_pending(
                f"sweep-term-{unique_id}",
                deadline=datetime.now(timezone.utc) - timedelta(seconds=1),
                base_url=base_url,
            )
            _task_scope()
            try:
                result = await a2a_pending_sweep_tick()
            finally:
                clear_log_context()
            assert _fired_count(result) >= 1
            after = await PlatformA2APendingCall.pending_by_id(
                f"sweep-term-{unique_id}"
            )
            assert after is not None and after.status == "expired"

    async def test_open_pending_not_swept(self, unique_id: str) -> None:
        _ = await _register_pending(
            f"sweep-open-{unique_id}",
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        _task_scope()
        try:
            result = await a2a_pending_sweep_tick()
        finally:
            clear_log_context()
        after = await PlatformA2APendingCall.pending_by_id(
            f"sweep-open-{unique_id}"
        )
        assert after is not None and after.status == "pending"
        assert _fired_count(result) >= 0


class TestTaskOutcome:
    def test_completed_outcome(self) -> None:
        outcome = a2a_task_outcome(
            {
                "id": "t",
                "status": {
                    "state": "TASK_STATE_COMPLETED",
                    "message": {"role": "ROLE_AGENT", "parts": [{"text": "ok"}]},
                },
                "artifacts": [{"artifactId": "a", "parts": [{"text": "ok"}]}],
            },
            "completed",
        )
        assert outcome["status"] == "completed"
        assert outcome["response"] == "ok"
        arts = outcome["artifacts"]
        assert isinstance(arts, list) and len(arts) == 1
        assert outcome["error"] is None

    def test_failed_outcome_extracts_message_detail(self) -> None:
        outcome = a2a_task_outcome(
            {
                "id": "t",
                "status": {
                    "state": "TASK_STATE_FAILED",
                    "message": {
                        "role": "ROLE_AGENT",
                        "parts": [{"text": "exploded"}],
                    },
                },
                "artifacts": [],
            },
            "failed",
        )
        assert outcome["status"] == "failed"
        assert outcome["error"] == "exploded"

    def test_token_hash_is_sha256(self) -> None:
        token = "abc"
        assert (
            hash_callback_token(token)
            == hashlib.sha256(token.encode()).hexdigest()
        )
