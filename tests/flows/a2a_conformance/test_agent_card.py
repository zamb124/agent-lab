"""Agent Card well-known + GET must be A2A 1.0."""

from __future__ import annotations

import pytest

from tests.flows._a2a_v1 import A2A_HEADERS
from tests.flows.a2a_conformance.helpers.flows import create_echo_flow, delete_flow
from tests.flows.a2a_conformance.helpers.schema import assert_valid_agent_card

pytestmark = [pytest.mark.asyncio]


async def test_agent_card_well_known_is_a2a_1_0(client, unique_id: str) -> None:
    flow_id = f"a2a_conf_card_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        response = await client.get(
            f"/flows/api/v1/{flow_id}/.well-known/agent-card.json",
            headers=A2A_HEADERS,
        )
        assert response.status_code == 200, response.text
        card = response.json()
        parsed = assert_valid_agent_card(card)
        assert parsed.capabilities.streaming is True
        assert parsed.capabilities.push_notifications is True
        assert parsed.capabilities.extended_agent_card is False
        assert "skills" in card
        assert isinstance(card["skills"], list) and len(card["skills"]) >= 1
        # Platform extension: branches mirrors skills (same list).
        assert "branches" in card
        assert card["branches"] == card["skills"]
        assert "kind" not in card
        assert "url" not in card or "supportedInterfaces" in card
        assert "protocolVersion" not in card  # singular 0.3 field forbidden at root
        iface = parsed.supported_interfaces[0]
        assert iface.protocol_binding == "JSONRPC"
        assert iface.protocol_version == "1.0"
    finally:
        await delete_flow(client, flow_id)


async def test_agent_card_get_matches_well_known(client, unique_id: str) -> None:
    flow_id = f"a2a_conf_card_get_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        well_known = await client.get(
            f"/flows/api/v1/{flow_id}/.well-known/agent-card.json",
            headers=A2A_HEADERS,
        )
        direct = await client.get(f"/flows/api/v1/{flow_id}", headers=A2A_HEADERS)
        assert well_known.status_code == 200
        assert direct.status_code == 200
        assert_valid_agent_card(well_known.json())
        assert_valid_agent_card(direct.json())
    finally:
        await delete_flow(client, flow_id)
