"""Runtime tests: flows product SLI logs (terminal, first chunk, react, tool, MCP)."""

from __future__ import annotations

import pytest

from apps.flows.src.clients.mcp_client import MCPClient
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.models.mcp import MCPServerConfig, MCPTransportType
from apps.flows.src.observability.flow_timing import (
    maybe_record_flow_first_content_chunk,
    maybe_record_flow_terminal,
    record_flow_task_enqueued,
)
from core.clients.llm import setup_mock_responses
from core.integrations.mcp import MCP_PROTOCOL_VERSION
from core.logging.attributes import (
    LOG_FLOW_FIRST_CHUNK_MS,
    LOG_FLOW_ID,
    LOG_FLOW_REACT_ITERATIONS,
    LOG_FLOW_TERMINAL_MS,
    LOG_MCP_SERVER_ID,
    LOG_MCP_TOOL_NAME,
    LOG_OPERATION_NAME,
    LOG_OPERATION_STATUS,
    LOG_TASK_ID,
    LOG_TOOL_DURATION_MS,
    LOG_TOOL_NAME,
)
from tests.fixtures.mcp_modes_stub import MCPStubMode, default_stub_tools
from tests.fixtures.observability_log_capture import (
    caplog_record_dict,
    find_caplog_record,
    find_caplog_records,
    require_log_fields,
    require_numeric_field,
    wait_for_caplog_event,
)
from tests.flows.durable_runtime_harness import run_flow, workflow_state
from tests.observability.contracts import (
    FLOW_FIRST_CONTENT_CHUNK,
    FLOW_REACT_COMPLETED,
    FLOW_TERMINAL,
    MCP_TOOL_CALL_FINISHED,
    TOOL_CALL_FINISHED,
)

pytestmark = pytest.mark.timeout(60)


def _save_flow(container, flow_config: dict[str, object]) -> None:
    return container.flow_repository.set(FlowConfig.model_validate(flow_config))


async def _persist_flow(container, flow_config: dict[str, object]) -> None:
    await _save_flow(container, flow_config)


@pytest.mark.asyncio
async def test_flow_terminal_emitted_after_enqueue(
    container,
    observability_caplog: pytest.LogCaptureFixture,
    unique_id: str,
) -> None:
    task_id = f"task-terminal-{unique_id}"
    flow_id = f"flow-terminal-{unique_id}"
    await record_flow_task_enqueued(container.redis_client, task_id=task_id, flow_id=flow_id)
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
            LOG_TASK_ID: str,
            LOG_FLOW_ID: str,
            LOG_FLOW_TERMINAL_MS: (int, float),
        },
    )
    assert fields[LOG_TASK_ID] == task_id
    assert fields[LOG_FLOW_ID] == flow_id
    require_numeric_field(fields, LOG_FLOW_TERMINAL_MS, min_value=0.0)


@pytest.mark.asyncio
async def test_flow_first_content_chunk_emitted_after_enqueue(
    container,
    observability_caplog: pytest.LogCaptureFixture,
    unique_id: str,
) -> None:
    task_id = f"task-chunk-{unique_id}"
    flow_id = f"flow-chunk-{unique_id}"
    await record_flow_task_enqueued(container.redis_client, task_id=task_id, flow_id=flow_id)
    await maybe_record_flow_first_content_chunk(
        container.redis_client,
        task_id=task_id,
        flow_id=flow_id,
        text="hello",
    )
    rec = find_caplog_record(
        observability_caplog,
        message=FLOW_FIRST_CONTENT_CHUNK.message,
        logger_name="apps.flows.src.observability.flow_timing",
    )
    fields = require_log_fields(
        rec,
        required={
            LOG_TASK_ID: str,
            LOG_FLOW_ID: str,
            LOG_FLOW_FIRST_CHUNK_MS: (int, float),
        },
    )
    require_numeric_field(fields, LOG_FLOW_FIRST_CHUNK_MS, min_value=0.0)


@pytest.mark.asyncio
async def test_flow_react_completed_emitted_after_llm_node(
    container,
    observability_caplog: pytest.LogCaptureFixture,
    unique_id: str,
) -> None:
    flow_id = f"react-metrics-{unique_id}"
    await _persist_flow(
        container,
        {
            "flow_id": flow_id,
            "name": "React metrics",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "node_id": "main",
                    "prompt": "test",
                    "llm": {"model": "mock-gpt-4"},
                    "tools": [{"tool_id": "calculator", "description": "calc"}],
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )
    setup_mock_responses(
        response_queue=[
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "1+1"}},
            "4",
        ]
    )
    state = workflow_state(flow_id=flow_id, unique_id=unique_id, content="calc")
    flow = await container.flow_factory.get_flow(flow_id)
    _ = await run_flow(container=container, flow=flow, state=state)

    rec = await wait_for_caplog_event(
        observability_caplog,
        message=FLOW_REACT_COMPLETED.message,
        logger_name="apps.flows.src.runtime.runners.llm_runner",
    )
    fields = require_log_fields(
        rec,
        required={
            LOG_FLOW_ID: str,
            LOG_FLOW_REACT_ITERATIONS: int,
        },
    )
    assert int(fields[LOG_FLOW_REACT_ITERATIONS]) >= 1


@pytest.mark.asyncio
async def test_tool_call_finished_emitted_for_builtin_tool(
    container,
    enable_observability_tracing: None,
    observability_caplog: pytest.LogCaptureFixture,
    unique_id: str,
) -> None:
    flow_id = f"tool-metrics-{unique_id}"
    await _persist_flow(
        container,
        {
            "flow_id": flow_id,
            "name": "Tool metrics",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "node_id": "main",
                    "prompt": "test",
                    "llm": {"model": "mock-gpt-4"},
                    "tools": [{"tool_id": "calculator", "description": "calc"}],
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )
    setup_mock_responses(
        response_queue=[
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "2+2"}},
            "4",
        ]
    )
    state = workflow_state(flow_id=flow_id, unique_id=unique_id, content="calc")
    flow = await container.flow_factory.get_flow(flow_id)
    _ = await run_flow(container=container, flow=flow, state=state)

    rec = find_caplog_record(
        observability_caplog,
        message=TOOL_CALL_FINISHED.message,
        logger_name="core.tracing.operation_log_mirror",
    )
    fields = require_log_fields(
        rec,
        required={
            LOG_TOOL_NAME: str,
            LOG_TOOL_DURATION_MS: (int, float),
            LOG_OPERATION_STATUS: str,
        },
    )
    assert fields[LOG_TOOL_NAME] == "calculator"
    assert fields[LOG_OPERATION_STATUS] == "ok"
    require_numeric_field(fields, LOG_TOOL_DURATION_MS, min_value=0.0)


@pytest.mark.asyncio
async def test_mcp_tool_call_operation_finished_ok(
    enable_observability_tracing: None,
    observability_caplog: pytest.LogCaptureFixture,
    mcp_modes_stub,
    unique_id: str,
) -> None:
    url, _state = mcp_modes_stub(MCPStubMode(tools=default_stub_tools()))
    server_id = f"mcp-ok-{unique_id}"
    client = MCPClient(
        MCPServerConfig(
            server_id=server_id,
            name="MCP OK",
            url=url,
            transport_type=MCPTransportType.HTTP,
            headers={},
            is_active=True,
            description="observability test",
        ),
        timeout=10.0,
    )
    tools = await client.list_tools()
    tool_name = tools[0].tool_name
    _ = await client.call_tool(tool_name, {"libraryName": "test"})

    rec = await wait_for_caplog_event(
        observability_caplog,
        message=MCP_TOOL_CALL_FINISHED.message,
        logger_name="core.tracing.operation_log_mirror",
        predicate=lambda fields: (
            fields.get(LOG_OPERATION_NAME) == "flows.mcp.tool_call"
            and fields.get(LOG_MCP_SERVER_ID) == server_id
        ),
    )
    fields = require_log_fields(
        rec,
        required={
            LOG_OPERATION_NAME: str,
            LOG_OPERATION_STATUS: str,
            LOG_MCP_SERVER_ID: str,
            LOG_MCP_TOOL_NAME: str,
        },
    )
    assert fields[LOG_OPERATION_NAME] == "flows.mcp.tool_call"
    assert fields[LOG_OPERATION_STATUS] == "ok"
    assert fields[LOG_MCP_SERVER_ID] == server_id
    assert fields[LOG_MCP_TOOL_NAME] == tool_name


@pytest.mark.asyncio
async def test_mcp_tool_call_operation_finished_error(
    enable_observability_tracing: None,
    observability_caplog: pytest.LogCaptureFixture,
    mcp_modes_stub,
    unique_id: str,
) -> None:
    url, _state = mcp_modes_stub(
        MCPStubMode(
            tools=default_stub_tools(),
            tool_call_rpc_error={"code": -32000, "message": "tool failed"},
        )
    )
    server_id = f"mcp-err-{unique_id}"
    client = MCPClient(
        MCPServerConfig(
            server_id=server_id,
            name="MCP ERR",
            url=url,
            transport_type=MCPTransportType.HTTP,
            headers={},
            is_active=True,
            description="observability test",
        ),
        timeout=10.0,
    )
    tools = await client.list_tools()
    with pytest.raises(Exception):
        _ = await client.call_tool(tools[0].tool_name, {"libraryName": "test"})

    records = find_caplog_records(
        observability_caplog,
        message=MCP_TOOL_CALL_FINISHED.message,
        logger_name="core.tracing.operation_log_mirror",
    )
    tool_call_records = [
        rec
        for rec in records
        if caplog_record_dict(rec).get(LOG_OPERATION_NAME) == "flows.mcp.tool_call"
        and caplog_record_dict(rec).get(LOG_MCP_SERVER_ID) == server_id
    ]
    assert tool_call_records, "ожидался operation_finished для flows.mcp.tool_call"
    fields = caplog_record_dict(tool_call_records[-1])
    assert fields.get(LOG_OPERATION_STATUS) == "ok"
