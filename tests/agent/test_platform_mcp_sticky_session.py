"""Sticky A2A context_id для Platform MCP (MCP session + device fallback)."""

from __future__ import annotations

import pytest

from apps.agent.platform_mcp import (
    _device_session_context_key,
    _mcp_initialize_instructions,
    _resolve_flow_context_id,
    _session_context_key,
)


def test_mcp_initialize_instructions_lara_only() -> None:
    lara_instructions = _mcp_initialize_instructions(toolkit_id="lara")
    assert lara_instructions is not None
    assert "flow_lara" in lara_instructions
    assert "NetWorkle" in lara_instructions
    assert _mcp_initialize_instructions(toolkit_id="networkle") is None
    assert _mcp_initialize_instructions(toolkit_id=None) is None


@pytest.mark.asyncio
async def test_sticky_reuses_mcp_session_context(container, unique_id: str) -> None:
    flow_id = f"flow_sticky_{unique_id}"
    mcp_session_id = f"mcp-{unique_id}"
    first = await _resolve_flow_context_id(
        container,
        mcp_session_id=mcp_session_id,
        device_id=None,
        flow_id=flow_id,
        explicit_context_id=None,
    )
    second = await _resolve_flow_context_id(
        container,
        mcp_session_id=mcp_session_id,
        device_id=None,
        flow_id=flow_id,
        explicit_context_id=None,
    )
    assert first == second
    stored = await container.redis_client.get(_session_context_key(mcp_session_id, flow_id))
    assert stored == first


@pytest.mark.asyncio
async def test_sticky_device_fallback_without_mcp_session(container, unique_id: str) -> None:
    flow_id = "lara"
    device_id = f"device-{unique_id}"
    first = await _resolve_flow_context_id(
        container,
        mcp_session_id=None,
        device_id=device_id,
        flow_id=flow_id,
        explicit_context_id=None,
    )
    second = await _resolve_flow_context_id(
        container,
        mcp_session_id=None,
        device_id=device_id,
        flow_id=flow_id,
        explicit_context_id=None,
    )
    assert first == second
    stored = await container.redis_client.get(_device_session_context_key(device_id, flow_id))
    assert stored == first


@pytest.mark.asyncio
async def test_sticky_explicit_context_id_wins(container, unique_id: str) -> None:
    flow_id = f"flow_explicit_{unique_id}"
    device_id = f"device-{unique_id}"
    explicit = f"ctx-explicit-{unique_id}"
    resolved = await _resolve_flow_context_id(
        container,
        mcp_session_id=None,
        device_id=device_id,
        flow_id=flow_id,
        explicit_context_id=explicit,
    )
    assert resolved == explicit
    again = await _resolve_flow_context_id(
        container,
        mcp_session_id=None,
        device_id=device_id,
        flow_id=flow_id,
        explicit_context_id=None,
    )
    assert again == explicit


@pytest.mark.asyncio
async def test_sticky_new_mcp_session_does_not_reuse_device_context(
    container, unique_id: str
) -> None:
    """New LinnexAgent dialog (new Mcp-Session-Id) must mint a new Lara context_id."""
    flow_id = "lara"
    device_id = f"device-{unique_id}"
    device_context = await _resolve_flow_context_id(
        container,
        mcp_session_id=None,
        device_id=device_id,
        flow_id=flow_id,
        explicit_context_id=None,
    )
    new_dialog_session = f"mcp-new-dialog-{unique_id}"
    dialog_context = await _resolve_flow_context_id(
        container,
        mcp_session_id=new_dialog_session,
        device_id=device_id,
        flow_id=flow_id,
        explicit_context_id=None,
    )
    assert dialog_context != device_context
    stored_session = await container.redis_client.get(
        _session_context_key(new_dialog_session, flow_id)
    )
    assert stored_session == dialog_context
    stored_device = await container.redis_client.get(
        _device_session_context_key(device_id, flow_id)
    )
    assert stored_device == device_context
