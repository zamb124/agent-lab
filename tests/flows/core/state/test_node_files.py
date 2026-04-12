"""Сбор node.files в state и валидация."""

import pytest

from apps.flows.src.services.flow_validator import FlowValidator, ValidationSeverity
from apps.flows.src.state.node_files import collect_flow_node_files, validate_node_files_list


def test_collect_flow_node_files_merges_in_stable_order() -> None:
    nodes = {
        "a": {"type": "code", "files": [{"name": "x.txt", "path": "/p1"}]},
        "b": {"type": "llm_node", "files": [{"name": "y.pdf", "path": "/p2", "mime_type": "application/pdf"}]},
    }
    got = collect_flow_node_files(nodes)
    assert len(got) == 2
    assert got[0]["name"] == "x.txt"
    assert got[1]["name"] == "y.pdf"
    assert got[1]["mime_type"] == "application/pdf"


def test_collect_flow_node_files_skips_empty() -> None:
    assert collect_flow_node_files({"n": {"type": "code"}}) == []
    assert collect_flow_node_files({"n": {"type": "code", "files": []}}) == []


def test_validate_node_files_list_rejects_bad_shape() -> None:
    with pytest.raises(ValueError, match="списком"):
        validate_node_files_list({}, node_id="n1")
    with pytest.raises(ValueError, match="name"):
        validate_node_files_list([{"path": "/x"}], node_id="n1")
    with pytest.raises(ValueError, match="path"):
        validate_node_files_list([{"name": "a"}], node_id="n1")


@pytest.mark.asyncio
async def test_flow_validator_invalid_node_files() -> None:
    v = FlowValidator(flow_repository=None, tool_repository=None, node_repository=None)
    nodes = {
        "main": {
            "type": "llm_node",
            "prompt": "hi",
            "files": [{"name": "", "path": "/x"}],
        }
    }
    edges = [{"from": "main", "to": None}]
    result = await v.validate(nodes=nodes, edges=edges, entry="main", variables={})
    assert result.valid is False
    codes = [e.code for e in result.errors if e.severity != ValidationSeverity.INFO]
    assert "invalid_node_files" in codes
