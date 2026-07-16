"""Sticky A2A context_id для Platform MCP (MCP session + device fallback)."""

from __future__ import annotations

import pytest

from apps.agent.platform_mcp import (
    _device_session_context_key,
    _resolve_flow_context_id,
    _session_context_key,
)


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
