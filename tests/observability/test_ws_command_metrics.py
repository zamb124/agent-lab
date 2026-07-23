"""Runtime tests: ws_command_finished structured log."""

from __future__ import annotations

import json

import pytest

from core.config import get_settings
from core.logging.attributes import (
    LOG_WS_COMMAND,
    LOG_WS_COMMAND_DURATION_MS,
    LOG_WS_COMMAND_STATUS,
)
from core.models.identity_models import User
from core.websocket.command_router import has_ws_command_handler, register_ws_command_handler
from core.websocket.router import _handle_command_frame
from tests.fixtures.observability_log_capture import (
    find_caplog_record,
    require_log_fields,
    require_numeric_field,
)
from tests.observability.contracts import WS_COMMAND_FINISHED

pytestmark = pytest.mark.timeout(30)

_TEST_COMMAND = "test/observability/ping_requested"


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, data: str) -> None:
        self.sent.append(data)


async def _observability_ping_handler(
    payload: dict[str, object],
    user: User,
) -> tuple[str, dict[str, object]]:
    _ = payload, user
    return "test/observability/ping_succeeded", {"ok": True}


@pytest.fixture(autouse=True)
def _register_observability_ws_command() -> None:
    if not has_ws_command_handler(_TEST_COMMAND):
        register_ws_command_handler(_TEST_COMMAND, _observability_ping_handler)


@pytest.mark.asyncio
async def test_ws_command_finished_emitted_for_successful_command(
    observability_caplog: pytest.LogCaptureFixture,
    unique_id: str,
) -> None:
    settings = get_settings()
    user = User(
        user_id=f"user-ws-{unique_id}",
        name="WS Test",
        active_company_id="system",
    )
    websocket = _FakeWebSocket()
    request_id = f"req-{unique_id}"
    await _handle_command_frame(
        websocket,
        {
            "request_id": request_id,
            "type": _TEST_COMMAND,
            "payload": {},
        },
        user,
        service_name=settings.server.name,
        connection_request_id=f"ws-conn-{unique_id}",
        connection_trace_id=f"ws-trace-{unique_id}",
    )
    assert websocket.sent

    rec = find_caplog_record(
        observability_caplog,
        message=WS_COMMAND_FINISHED.message,
        logger_name="core.websocket.router",
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

    reply = json.loads(websocket.sent[-1])
    assert reply["request_id"] == request_id
    assert reply["type"] == "test/observability/ping_succeeded"
