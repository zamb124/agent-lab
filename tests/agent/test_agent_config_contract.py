"""Контракт agent-секции conf.json и AgentSettings."""

from __future__ import annotations

import json
from pathlib import Path

from apps.agent.config import AgentSettings

REPO_ROOT = Path(__file__).resolve().parents[2]
CONF_PATH = REPO_ROOT / "conf.json"


def test_conf_agent_section_covers_agent_settings_fields() -> None:
    conf_payload = json.loads(CONF_PATH.read_text(encoding="utf-8"))
    agent_section = conf_payload.get("agent")
    assert isinstance(agent_section, dict)
    settings = AgentSettings.model_validate(agent_section)
    assert settings.pairing_rate_limit_per_hour == 20
    assert settings.register_rate_limit_per_hour == 60
    assert settings.pairing_ttl_seconds == 600
    assert settings.tunnel_online_ttl_seconds == 120
