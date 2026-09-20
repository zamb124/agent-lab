"""Runtime tests: ws_command_finished structured log."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.context import reset_context, set_context
from core.events.contract import PlatformEvent
from core.logging.attributes import (
    LOG_WS_COMMAND,
    LOG_WS_COMMAND_DURATION_MS,
    LOG_WS_COMMAND_STATUS,
)
from core.models.context_models import Context
from core.models.identity_models import User
from core.realtime.command_http import execute_realtime_command
from core.realtime.models import RealtimeCommandAccepted
from core.types import JsonObject
from core.websocket.command_router import has_ws_command_handler, register_ws_command_handler
from tests.fixtures.observability_log_capture import (
    find_caplog_record,
    require_log_fields,
    require_numeric_field,
)
from tests.observability.contracts import WS_COMMAND_FINISHED

pytestmark = pytest.mark.timeout(30)

_TEST_COMMAND = "test/observability/ping_requested"


async def _observability_ping_handler(
    payload: JsonObject,
    user: User,
) -> JsonObject:
    _ = payload, user
    return {"ok": True}


@pytest.fixture(autouse=True)
def _register_observability_ws_command() -> None:
    if not has_ws_command_handler(_TEST_COMMAND):
        register_ws_command_handler(_TEST_COMMAND, _observability_ping_handler)


@pytest.mark.asyncio
async def test_ws_command_finished_emitted_for_successful_command(
    observability_caplog: pytest.LogCaptureFixture,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published: list[tuple[str, str, object]] = []

    async def _capture_publish(
        user_id: str,
        type: str,
        payload: object = None,
        **kwargs: object,
    ) -> None:
        _ = kwargs
        published.append((user_id, type, payload))

    monkeypatch.setattr("core.realtime.command_http.publish_event_to_user", _capture_publish)

    user = User(
        user_id=f"user-ws-{unique_id}",
        name="WS Test",
        active_company_id="system",
    )
    context = Context(user=user, channel="ws")
    token = set_context(context)
    event = PlatformEvent(
        event_id=f"e-{unique_id}",
        type=_TEST_COMMAND,
        company_id="system",
        payload={},
    )
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(container=object(), settings=object()),
        )
    )
    try:
        accepted = await execute_realtime_command(event, request)  # type: ignore[arg-type]
    finally:
        reset_context(token)

    assert isinstance(accepted, RealtimeCommandAccepted)
    assert accepted.event_id == event.event_id
    assert published == [(user.user_id, "test/observability/ping_succeeded", {"ok": True})]

    rec = find_caplog_record(
        observability_caplog,
        message=WS_COMMAND_FINISHED.message,
        logger_name="core.realtime.command_http",
    )
    fields = require_log_fields(
        rec,
        required={
            LOG_WS_COMMAND: str,
            LOG_WS_COMMAND_DURATION_MS: (int, float),
            LOG_WS_COMMAND_STATUS: str,
        },
    )
    assert fields[LOG_WS_COMMAND] == _TEST_COMMAND
    assert fields[LOG_WS_COMMAND_STATUS] == "ok"
    require_numeric_field(fields, LOG_WS_COMMAND_DURATION_MS, min_value=0.0)
