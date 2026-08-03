"""Unit tests for LinnexAgent device tunnel tools."""

from __future__ import annotations

import pytest

from apps.flows.tools.device_tools import _require_device_id, device_tools_list
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
    container, unique_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from apps.flows.src.clients.device_client import DeviceClient
    from apps.flows.src.container_contracts import as_flow_runtime_container
    from apps.flows.src.container_state import (
        get_current_container,
        reset_current_container,
        set_current_container,
    )

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
    previous = get_current_container()
    set_current_container(as_flow_runtime_container(container))
    try:
        with pytest.raises(ValueError, match="offline"):
            _ = await device_tools_list.run({}, state)
    finally:
        if previous is not None:
            set_current_container(previous)
        else:
            reset_current_container()
