"""Runtime tests: TaskIQ pickup and flow terminal via worker path."""

from __future__ import annotations

import time

import pytest
from taskiq import TaskiqMessage, TaskiqResult

from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.observability.flow_timing import maybe_record_flow_terminal, record_flow_task_enqueued
from apps.flows.src.tasks.flow_tasks import process_flow_task
from apps.flows.src.tasks.task_names import TASK_PROCESS_FLOW
from core.clients.llm import setup_mock_responses
from core.context import Context, set_context
from core.logging.attributes import LOG_TASK_NAME, LOG_TASK_QUEUE_WAIT_MS
from core.models.identity_models import User
from core.tasks.logging_middleware import LoggingMiddleware
from core.tasks.message_contract import set_task_message_string_label
from core.types import JsonValue
from tests.fixtures.observability_log_capture import find_caplog_record, require_log_fields, require_numeric_field
from tests.flows.durable_runtime_harness import workflow_state
from tests.observability.contracts import FLOW_TERMINAL, TASK_STARTED_PICKUP

pytestmark = [pytest.mark.real_taskiq, pytest.mark.timeout(180, func_only=False)]


@pytest.fixture(autouse=True)
def _use_worker(taskiq_worker, container):
    container.use_worker = True
    yield
    container.use_worker = False


@pytest.mark.asyncio
async def test_task_queue_wait_ms_emitted_by_logging_middleware(
    observability_caplog: pytest.LogCaptureFixture,
    unique_id: str,
) -> None:
    enqueued_at = time.time() - 0.25
    message = TaskiqMessage(
        task_id=f"task-pickup-{unique_id}",
        task_name=TASK_PROCESS_FLOW,
        labels={
            "request_id": f"req-{unique_id}",
            "trace_id": f"trace-{unique_id}",
            "service_name": "flows_worker",
        },
        labels_types={},
        args=[],
        kwargs={},
    )
    set_task_message_string_label(message, "enqueued_at", str(enqueued_at))
    middleware = LoggingMiddleware(queue_name="flows_worker", service_name="flows_worker")

    processed = await middleware.pre_execute(message)
    assert processed is message
    await middleware.post_execute(
        message,
        TaskiqResult[JsonValue](
            is_err=False,
            return_value=None,
            execution_time=0.01,
            labels=message.labels,
        ),
    )

    rec = find_caplog_record(
        observability_caplog,
        message=TASK_STARTED_PICKUP.message,
        logger_name="platform.task",
    )
    fields = require_log_fields(
        rec,
        required={
            LOG_TASK_NAME: str,
            LOG_TASK_QUEUE_WAIT_MS: (int, float),
        },
    )
    assert fields[LOG_TASK_NAME] == TASK_PROCESS_FLOW
    require_numeric_field(fields, LOG_TASK_QUEUE_WAIT_MS, min_value=0.0)


@pytest.mark.asyncio
async def test_flow_terminal_via_process_flow_task_in_worker_context(
    app,
    container,
    observability_caplog: pytest.LogCaptureFixture,
    unique_id: str,
    mock_context,
) -> None:
    flow_id = f"flow-worker-terminal-{unique_id}"
    await container.flow_repository.set(
        FlowConfig.model_validate(
            {
                "flow_id": flow_id,
                "name": "Worker terminal",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "node_id": "main",
                        "prompt": "reply",
                        "llm": {"model": "mock-gpt-4"},
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
            }
        )
    )
    state = workflow_state(flow_id=flow_id, unique_id=unique_id, content="hi")
    task_id = state.task_id
    await record_flow_task_enqueued(container.redis_client, task_id=task_id, flow_id=flow_id)

    setup_mock_responses(response_queue=["hello from worker"])
    ctx = Context.from_dict(mock_context.to_dict())
    ctx.session_id = state.session_id
    set_context(ctx)

    _ = await process_flow_task(
        flow_id=flow_id,
        session_id=state.session_id,
        user_id=state.user_id,
        content=state.content,
        task_id=task_id,
        context_id=state.context_id,
        context_data=mock_context.to_dict(),
    )
    await maybe_record_flow_terminal(
        container.redis_client,
        task_id=task_id,
        flow_id=flow_id,
        terminal_state="completed",
    )

    rec = find_caplog_record(
        observability_caplog,
        message=FLOW_TERMINAL.message,
        logger_name="apps.flows.src.observability.flow_timing",
    )
    fields = require_log_fields(
        rec,
        required={
            "task.id": str,
            "flow.id": str,
            "flow.terminal_ms": (int, float),
        },
    )
    assert fields["task.id"] == task_id
    assert fields["flow.id"] == flow_id
