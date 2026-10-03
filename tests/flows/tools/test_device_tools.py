"""Unit tests for LinnexAgent device tunnel tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.flows.tools.device.device_tools import _require_device_id, device_tools_list
from core.state import ExecutionState


def test_require_device_id_missing_raises() -> None:
    state = ExecutionState.create(
        task_id="task-1",
        context_id="ctx-1",
        user_id="user-1",
        session_id="lara:ctx-1",
    )
    with pytest.raises(ValueError, match="device_id is missing"):
        _ = _require_device_id(state)


def test_require_device_id_reads_variables() -> None:
    state = ExecutionState.create(
        task_id="task-1",
        context_id="ctx-1",
        user_id="user-1",
        session_id="lara:ctx-1",
    )
    state.variables = {"device_id": "device-abc"}
    assert _require_device_id(state) == "device-abc"


@pytest.mark.asyncio
async def test_device_tools_list_propagates_tunnel_error(
    unique_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from apps.flows.src.services.device_client import DeviceClient

    async def _offline_tools_list(self: DeviceClient, *_args: object, **_kwargs: object) -> object:
        raise ValueError(f"Device tunnel offline: offline-device-{unique_id}")

    monkeypatch.setattr(DeviceClient, "tools_list", _offline_tools_list)

    context_id = f"ctx-{unique_id}"
    state = ExecutionState.create(
        task_id=f"task-{unique_id}",
        context_id=context_id,
        user_id="user-1",
        session_id=f"lara:{context_id}",
    )
    state.variables = {"device_id": f"offline-device-{unique_id}"}
    bound = device_tools_list.with_dependencies([DeviceClient(MagicMock())])
    with pytest.raises(ValueError, match="offline"):
        _ = await bound.run({}, state)
