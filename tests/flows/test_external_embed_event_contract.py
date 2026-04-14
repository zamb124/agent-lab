from __future__ import annotations

import json
from pathlib import Path


def test_external_embed_event_contract_v1_has_required_sections() -> None:
    contract_path = Path(
        "core/frontend/static/lib/embed-chat/external-embed-event-contract-v1.json"
    )
    payload = json.loads(contract_path.read_text(encoding="utf-8"))

    assert payload["contract_version"] == "1.0.0"
    assert payload["namespace"] == "assistant"
    assert payload["event_envelope"]["versioning_policy"]["semver"] == "major.minor.patch"

    event_types = {event["type"] for event in payload["events"]}
    assert "assistant:action_invoked" in event_types
    assert "assistant:action_previewed" in event_types
    assert "assistant:action_applied" in event_types
    assert "assistant:ack" in event_types
    assert "assistant:nack" in event_types
