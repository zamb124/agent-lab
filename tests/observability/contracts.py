"""Typed contracts for product metric completion logs."""

from __future__ import annotations

from dataclasses import dataclass

from core.logging.attributes import (
    EVENT_BILLING_SETTLEMENT_LAG,
    EVENT_FLOW_FIRST_CONTENT_CHUNK,
    EVENT_FLOW_REACT_COMPLETED,
    EVENT_FLOW_TERMINAL,
    EVENT_HANDOFF_WALL_TIME,
    EVENT_HITL_OPERATOR_RESPONDED,
    EVENT_LLM_CONTEXT_COMPILED,
    EVENT_LLM_STREAM_RESPONSE,
    EVENT_OPERATION_FINISHED,
    EVENT_TASK_STARTED,
    EVENT_TOOL_CALL_FINISHED,
    EVENT_VOICE_TTS_RESPONSE,
    EVENT_WS_COMMAND_FINISHED,
    LOG_BILLING_SETTLEMENT_LAG_MS,
    LOG_FLOW_FIRST_CHUNK_MS,
    LOG_FLOW_ID,
    LOG_FLOW_REACT_ITERATIONS,
    LOG_FLOW_TERMINAL_MS,
    LOG_HANDOFF_TARGET_FLOW_ID,
    LOG_HANDOFF_WALL_MS,
    LOG_HITL_QUEUE_SLUG,
    LOG_HITL_WAIT_MS,
    LOG_HITL_WORK_ITEM_ID,
    LOG_LLM_CONTEXT_COMPILE_MS,
    LOG_LLM_MODEL,
    LOG_LLM_PROVIDER,
    LOG_LLM_TTFT_MS,
    LOG_MCP_SERVER_ID,
    LOG_MCP_TOOL_NAME,
    LOG_OPERATION_DURATION_MS,
    LOG_OPERATION_NAME,
    LOG_OPERATION_STATUS,
    LOG_TASK_ID,
    LOG_TASK_NAME,
    LOG_TASK_QUEUE_WAIT_MS,
    LOG_TOOL_DURATION_MS,
    LOG_TOOL_NAME,
    LOG_TTS_PROVIDER,
    LOG_TTS_TTFA_MS,
    LOG_WS_COMMAND,
    LOG_WS_COMMAND_DURATION_MS,
    LOG_WS_COMMAND_STATUS,
)


@dataclass(frozen=True)
class MetricLogContract:
    message: str
    unwrap_field: str
    required_fields: tuple[str, ...]


OPERATION_FINISHED = MetricLogContract(
    message=EVENT_OPERATION_FINISHED,
    unwrap_field=LOG_OPERATION_DURATION_MS,
    required_fields=(
        LOG_OPERATION_NAME,
        LOG_OPERATION_STATUS,
        LOG_OPERATION_DURATION_MS,
    ),
)

TOOL_CALL_FINISHED = MetricLogContract(
    message=EVENT_TOOL_CALL_FINISHED,
    unwrap_field=LOG_TOOL_DURATION_MS,
    required_fields=(
        LOG_TOOL_NAME,
        LOG_OPERATION_STATUS,
        LOG_TOOL_DURATION_MS,
    ),
)

FLOW_TERMINAL = MetricLogContract(
    message=EVENT_FLOW_TERMINAL,
    unwrap_field=LOG_FLOW_TERMINAL_MS,
    required_fields=(
        LOG_TASK_ID,
        LOG_FLOW_ID,
        LOG_FLOW_TERMINAL_MS,
    ),
)

FLOW_FIRST_CONTENT_CHUNK = MetricLogContract(
    message=EVENT_FLOW_FIRST_CONTENT_CHUNK,
    unwrap_field=LOG_FLOW_FIRST_CHUNK_MS,
    required_fields=(
        LOG_TASK_ID,
        LOG_FLOW_ID,
        LOG_FLOW_FIRST_CHUNK_MS,
    ),
)

FLOW_REACT_COMPLETED = MetricLogContract(
    message=EVENT_FLOW_REACT_COMPLETED,
    unwrap_field=LOG_FLOW_REACT_ITERATIONS,
    required_fields=(
        LOG_FLOW_ID,
        LOG_FLOW_REACT_ITERATIONS,
    ),
)

HANDOFF_WALL_TIME = MetricLogContract(
    message=EVENT_HANDOFF_WALL_TIME,
    unwrap_field=LOG_HANDOFF_WALL_MS,
    required_fields=(
        LOG_HANDOFF_WALL_MS,
        LOG_HANDOFF_TARGET_FLOW_ID,
    ),
)

HITL_OPERATOR_RESPONDED = MetricLogContract(
    message=EVENT_HITL_OPERATOR_RESPONDED,
    unwrap_field=LOG_HITL_WAIT_MS,
    required_fields=(
        LOG_HITL_WAIT_MS,
        LOG_HITL_WORK_ITEM_ID,
        LOG_HITL_QUEUE_SLUG,
    ),
)

LLM_CONTEXT_COMPILED = MetricLogContract(
    message=EVENT_LLM_CONTEXT_COMPILED,
    unwrap_field=LOG_LLM_CONTEXT_COMPILE_MS,
    required_fields=(
        LOG_LLM_CONTEXT_COMPILE_MS,
        LOG_LLM_PROVIDER,
        LOG_LLM_MODEL,
    ),
)

LLM_STREAM_RESPONSE = MetricLogContract(
    message=EVENT_LLM_STREAM_RESPONSE,
    unwrap_field=LOG_LLM_TTFT_MS,
    required_fields=(
        LOG_LLM_PROVIDER,
        LOG_LLM_MODEL,
        LOG_LLM_TTFT_MS,
    ),
)

BILLING_SETTLEMENT_LAG = MetricLogContract(
    message=EVENT_BILLING_SETTLEMENT_LAG,
    unwrap_field=LOG_BILLING_SETTLEMENT_LAG_MS,
    required_fields=(
        LOG_BILLING_SETTLEMENT_LAG_MS,
        LOG_OPERATION_NAME,
    ),
)

WS_COMMAND_FINISHED = MetricLogContract(
    message=EVENT_WS_COMMAND_FINISHED,
    unwrap_field=LOG_WS_COMMAND_DURATION_MS,
    required_fields=(
        LOG_WS_COMMAND,
        LOG_WS_COMMAND_DURATION_MS,
        LOG_WS_COMMAND_STATUS,
    ),
)

VOICE_TTS_RESPONSE = MetricLogContract(
    message=EVENT_VOICE_TTS_RESPONSE,
    unwrap_field=LOG_TTS_TTFA_MS,
    required_fields=(
        LOG_TTS_PROVIDER,
        LOG_TTS_TTFA_MS,
    ),
)

TASK_STARTED_PICKUP = MetricLogContract(
    message=EVENT_TASK_STARTED,
    unwrap_field=LOG_TASK_QUEUE_WAIT_MS,
    required_fields=(
        LOG_TASK_NAME,
        LOG_TASK_QUEUE_WAIT_MS,
    ),
)

MCP_TOOL_CALL_FINISHED = MetricLogContract(
    message=EVENT_OPERATION_FINISHED,
    unwrap_field=LOG_OPERATION_DURATION_MS,
    required_fields=(
        LOG_OPERATION_NAME,
        LOG_OPERATION_STATUS,
        LOG_MCP_SERVER_ID,
        LOG_MCP_TOOL_NAME,
    ),
)

RAG_SEARCH_FINISHED = MetricLogContract(
    message=EVENT_OPERATION_FINISHED,
    unwrap_field=LOG_OPERATION_DURATION_MS,
    required_fields=(
        LOG_OPERATION_NAME,
        LOG_OPERATION_STATUS,
    ),
)

ALL_PRODUCT_METRIC_CONTRACTS: tuple[MetricLogContract, ...] = (
    OPERATION_FINISHED,
    TOOL_CALL_FINISHED,
    FLOW_TERMINAL,
    FLOW_FIRST_CONTENT_CHUNK,
    FLOW_REACT_COMPLETED,
    HANDOFF_WALL_TIME,
    HITL_OPERATOR_RESPONDED,
    LLM_CONTEXT_COMPILED,
    LLM_STREAM_RESPONSE,
    BILLING_SETTLEMENT_LAG,
    WS_COMMAND_FINISHED,
    VOICE_TTS_RESPONSE,
    TASK_STARTED_PICKUP,
    MCP_TOOL_CALL_FINISHED,
    RAG_SEARCH_FINISHED,
)
