"""Сбор node.files в state и валидация."""

import pytest

from apps.flows.src.services.flow_validator import FlowValidator, ValidationSeverity
from apps.flows.src.state.node_files import collect_flow_node_files, validate_node_files_list


def test_collect_flow_node_files_merges_in_stable_order() -> None:
    nodes = {
        "a": {
            "type": "code",
            "files": [
                {
                    "original_name": "x.txt",
                    "url": "/p1",
                    "content_type": "text/plain",
                    "file_size": 1,
                }
            ],
        },
        "b": {
            "type": "llm_node",
            "files": [
                {
                    "original_name": "y.pdf",
                    "url": "/p2",
                    "content_type": "application/pdf",
                    "file_size": 2,
                }
            ],
        },
    }
    got = collect_flow_node_files(nodes)
    assert len(got) == 2
    assert got[0].original_name == "x.txt"
    assert got[1].original_name == "y.pdf"
    assert got[1].content_type == "application/pdf"


def test_collect_flow_node_files_skips_empty() -> None:
    assert collect_flow_node_files({"n": {"type": "code"}}) == []
    assert collect_flow_node_files({"n": {"type": "code", "files": []}}) == []


def test_validate_node_files_list_rejects_bad_shape() -> None:
    with pytest.raises(ValueError, match="списком"):
        validate_node_files_list({}, node_id="n1")
    with pytest.raises(ValueError, match="original_name"):
        validate_node_files_list(
            [{"url": "/x", "content_type": "text/plain", "file_size": 1}],
            node_id="n1",
        )
    with pytest.raises(ValueError, match="file_id или url"):
        validate_node_files_list(
            [{"original_name": "a", "content_type": "text/plain", "file_size": 1}],
            node_id="n1",
        )


@pytest.mark.asyncio
async def test_flow_validator_invalid_node_files() -> None:
    v = FlowValidator(flow_repository=None, tool_repository=None, node_repository=None)
    nodes = {
        "main": {
            "type": "llm_node",
            "prompt": "hi",
            "files": [{"original_name": "", "url": "/x"}],
        }
    }
    edges = [{"from": "main", "to": None}]
    result = await v.validate(nodes=nodes, edges=edges, entry="main", variables={})
    assert result.valid is False
    codes = [e.code for e in result.errors if e.severity != ValidationSeverity.INFO]
    assert "invalid_node_files" in codes
