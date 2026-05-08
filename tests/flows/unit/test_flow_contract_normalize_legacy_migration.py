"""Нормализация легаси skills / skill_ids при чтении конфига (как agents_0005)."""

from __future__ import annotations

import pytest

from apps.flows.src.models import FlowConfig
from apps.flows.src.services.flow_contract_normalize import normalize_flow_config_dict


def _minimal_local_flow() -> dict:
    return {
        "flow_id": "f_legacy_norm",
        "name": "Agent",
        "type": "local",
        "entry": "main",
        "nodes": {
            "main": {
                "node_id": "main",
                "type": "code",
                "code": "async def run(state):\n    return state",
            }
        },
        "edges": [{"from": "main", "to": None}],
    }


def test_normalize_migrates_skills_to_branches() -> None:
    raw = _minimal_local_flow()
    raw["skills"] = {
        "alt": {
            "name": "Alt",
            "entry": "main",
            "nodes": {
                "main": {
                    "node_id": "main",
                    "type": "code",
                    "code": "async def run(state):\n    return state",
                }
            },
            "edges": [],
        }
    }
    norm = normalize_flow_config_dict(raw)
    assert "skills" not in norm
    assert "alt" in norm["branches"]
    cfg = FlowConfig.model_validate(norm)
    assert "alt" in cfg.branches


def test_normalize_migrates_evaluation_skill_ids_to_branch_ids() -> None:
    raw = _minimal_local_flow()
    raw["evaluation"] = {
        "c1": {
            "name": "Case",
            "turns": [],
            "skill_ids": ["alt"],
        }
    }
    norm = normalize_flow_config_dict(raw)
    case = norm["evaluation"]["c1"]
    assert case["branch_ids"] == ["alt"]
    assert "skill_ids" not in case
    FlowConfig.model_validate(norm)


def test_normalize_rejects_both_branches_and_skills() -> None:
    raw = _minimal_local_flow()
    raw["branches"] = {"x": {"name": "X"}}
    raw["skills"] = {"y": {"name": "Y"}}
    with pytest.raises(ValueError, match="одновременно"):
        normalize_flow_config_dict(raw)


def test_normalize_rejects_evaluation_skill_ids_and_branch_ids() -> None:
    raw = _minimal_local_flow()
    raw["evaluation"] = {
        "c1": {
            "name": "Case",
            "turns": [],
            "skill_ids": ["a"],
            "branch_ids": ["b"],
        }
    }
    with pytest.raises(ValueError, match="одновременно"):
        normalize_flow_config_dict(raw)


def test_normalize_merges_external_api_parameters_header_default_into_headers() -> None:
    raw = _minimal_local_flow()
    raw["nodes"]["ext"] = {
        "node_id": "ext",
        "type": "external_api",
        "url": "https://api.example/x",
        "headers": {"X-Existing": "keep"},
        "parameters": [
            {
                "name": "X-Trace-Id",
                "location": "header",
                "default": "@var:tid",
                "type": "string",
            }
        ],
    }
    norm = normalize_flow_config_dict(raw)
    ext = norm["nodes"]["ext"]
    assert ext.get("parameters") is None
    assert ext["headers"]["X-Existing"] == "keep"
    assert ext["headers"]["X-Trace-Id"] == "@var:tid"


def test_normalize_strip_external_api_parameters_non_header() -> None:
    raw = _minimal_local_flow()
    raw["nodes"]["ext"] = {
        "node_id": "ext",
        "type": "external_api",
        "url": "https://api.example/items/{item_id}",
        "headers": {},
        "parameters": [
            {"name": "city", "location": "query", "type": "string"},
            {"name": "item_id", "location": "path", "type": "string"},
        ],
    }
    norm = normalize_flow_config_dict(raw)
    assert norm["nodes"]["ext"].get("parameters") is None
