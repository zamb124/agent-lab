"""Prod-like: Loki/Tempo observability — REST и `op_*` один handler."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import replace
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from apps.flows.di import FlowsDi
from apps.flows.realtime.observability_operations import (
    op_flows_logs_by_trace,
    op_flows_traces_by_trace,
    op_flows_traces_handoff_chain,
    op_flows_traces_search,
)
from apps.flows.src.models.observability_api import (
    ObservabilityLogsQueryPayload,
    ObservabilityTraceQueryPayload,
    ObservabilityTraceSearchPayload,
)
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from core.tracing import attributes as trace_attr
from core.tracing.models import Span
from core.websocket import WsCommandError
from tests.fixtures.ai_provider_defaults import make_test_company
from tests.flows.api.test_observability_logs_api import (
    _SAMPLE_LOG_ENTRIES,
    MockLokiClient,
    _restore_loki_client_cache,
    _swap_loki_client_cache,
)
from tests.flows.api.test_traces_tempo_api import (
    _SAMPLE_SPANS,
    MockTempoClient,
    _restore_mock_tempo,
    _set_mock_tempo,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]


@contextmanager
def _system_scope(system_user_id: str) -> Generator[User]:
    user = User(user_id=system_user_id, name="System")
    token = set_context(
        Context(
            user=user,
            active_company=make_test_company(company_id="system", name="System"),
            channel="api",
            active_namespace="default",
        )
    )
    try:
        yield user
    finally:
        reset_context(token)


async def test_logs_by_trace_rest_match_op(
    client: AsyncClient,
    app: object,
    di: FlowsDi,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    previous = _swap_loki_client_cache(
        app, di, MockLokiClient(entries=_SAMPLE_LOG_ENTRIES)
    )
    try:
        http = await client.get(
            "/flows/api/v1/observability/logs/by-trace/abc123",
            headers=auth_headers_system,
        )
        assert http.status_code == 200, http.text
        with _system_scope(system_user_id) as user:
            op_result = await op_flows_logs_by_trace(
                ObservabilityLogsQueryPayload(trace_id="abc123"),
                user=user,
                di=replace(di, loki_client=MockLokiClient(entries=_SAMPLE_LOG_ENTRIES)),
            )
        assert op_result.model_dump(mode="json") == http.json()
    finally:
        _restore_loki_client_cache(app, previous)


async def test_logs_loki_unconfigured_rest_match_op(
    client: AsyncClient,
    app: object,
    di: FlowsDi,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    previous = _swap_loki_client_cache(app, di, MockLokiClient(configured=False))
    try:
        http = await client.get(
            "/flows/api/v1/observability/logs/by-trace/abc123",
            headers=auth_headers_system,
        )
        assert http.status_code == 503, http.text
        assert http.json()["error_code"] == "unavailable"
        with _system_scope(system_user_id) as user:
            with pytest.raises(WsCommandError) as exc_info:
                _ = await op_flows_logs_by_trace(
                    ObservabilityLogsQueryPayload(trace_id="abc123"),
                    user=user,
                    di=replace(di, loki_client=MockLokiClient(configured=False)),
                )
        assert exc_info.value.code == "unavailable"
    finally:
        _restore_loki_client_cache(app, previous)


async def test_traces_by_trace_rest_match_op(
    client: AsyncClient,
    app: object,
    di: FlowsDi,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    prev = _set_mock_tempo(app, di, MockTempoClient(spans=_SAMPLE_SPANS))
    try:
        http = await client.get(
            "/flows/api/v1/traces/trace/trace001",
            headers=auth_headers_system,
        )
        assert http.status_code == 200, http.text
        with _system_scope(system_user_id) as user:
            op_result = await op_flows_traces_by_trace(
                ObservabilityTraceQueryPayload(trace_id="trace001"),
                user=user,
                di=replace(di, tempo_client=MockTempoClient(spans=_SAMPLE_SPANS)),
            )
        assert op_result.model_dump(mode="json") == http.json()
    finally:
        _restore_mock_tempo(app, prev)


async def test_traces_tempo_unavailable_rest_match_op(
    client: AsyncClient,
    app: object,
    di: FlowsDi,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    prev = _set_mock_tempo(app, di, MockTempoClient(raise_error=True))
    try:
        http = await client.get(
            "/flows/api/v1/traces/trace/trace001",
            headers=auth_headers_system,
        )
        assert http.status_code == 503, http.text
        assert http.json()["error_code"] == "unavailable"
        with _system_scope(system_user_id) as user:
            with pytest.raises(WsCommandError) as exc_info:
                _ = await op_flows_traces_by_trace(
                    ObservabilityTraceQueryPayload(trace_id="trace001"),
                    user=user,
                    di=replace(di, tempo_client=MockTempoClient(raise_error=True)),
                )
        assert exc_info.value.code == "unavailable"
    finally:
        _restore_mock_tempo(app, prev)


async def test_traces_search_rest_match_op(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    flow_id = f"obs_search_{unique_id}"
    now = datetime.now(timezone.utc)
    await Span.insert_span_once(
        Span(
            span_id=f"span-{unique_id}",
            trace_id=f"trace-{unique_id}",
            parent_span_id=None,
            operation_name=f"flow.{flow_id}",
            kind="INTERNAL",
            start_time=now,
            end_time=now,
            duration_ms=1,
            status="OK",
            service_name="flows",
            company_id="system",
            namespace="default",
            user_id=system_user_id,
            user_name=None,
            user_groups=None,
            session_auth=None,
            session_agent=None,
            channel=None,
            event_type=None,
            resource_type="flow",
            resource_id=flow_id,
            attributes={trace_attr.ATTR_FLOW_ID: flow_id},
            events=[],
        )
    )
    http = await client.get(
        "/flows/api/v1/traces/search",
        headers=auth_headers_system,
        params={"flow_id": flow_id, "limit": 20},
    )
    assert http.status_code == 200, http.text
    body = http.json()
    assert body["traces_count"] >= 1
    with _system_scope(system_user_id) as user:
        op_result = await op_flows_traces_search(
            ObservabilityTraceSearchPayload(flow_id=flow_id, limit=20),
            user=user,
            di=di,
        )
    assert op_result.model_dump(mode="json") == body


async def test_traces_handoff_missing_session_rest_match_op(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    parent_session_id = f"missing-handoff-{unique_id}:ctx"
    http = await client.get(
        f"/flows/api/v1/traces/handoff-chain/{parent_session_id}",
        headers=auth_headers_system,
    )
    assert http.status_code == 404, http.text
    assert http.json()["error_code"] == "not_found"
    with _system_scope(system_user_id) as user:
        with pytest.raises(WsCommandError) as exc_info:
            _ = await op_flows_traces_handoff_chain(
                ObservabilityTraceQueryPayload(parent_session_id=parent_session_id),
                user=user,
                di=di,
            )
    assert exc_info.value.code == "not_found"
