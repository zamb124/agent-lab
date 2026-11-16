"""Сборка и раскладка bundle без сервера."""

from __future__ import annotations

from pathlib import Path

from platform_sdk.bundle import assemble_bundle, layout_bundle
from platform_sdk.errors import PlatformCliError


def test_layout_then_assemble_restores_prompt_and_code(tmp_path: Path) -> None:
    flow = {
        "flow_id": "demo",
        "name": "Demo",
        "entry": "main",
        "nodes": {
            "main": {
                "type": "llm_node",
                "prompt": "Hello\nworld\n",
                "language": "python",
                "code": "async def run(args, state):\n    return state\n",
                "output_schema": {"type": "object"},
            }
        },
        "edges": [{"from_node": "main", "to_node": None}],
    }
    layout_bundle(tmp_path, flow)
    assembled = assemble_bundle(tmp_path)
    node = assembled["nodes"]["main"]
    assert isinstance(node, dict)
    assert node["prompt"] == "Hello\nworld\n"
    assert node["code"] == "async def run(args, state):\n    return state\n"
    assert node["output_schema"] == {"type": "object"}
    assert "output_schema_file" not in node


def test_function_field_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "flow.yaml").write_text(
        "flow_id: demo\nname: Demo\nentry: main\nnodes:\n  main:\n    type: code\n    function: app.mod.fn\n",
        encoding="utf-8",
    )
    try:
        assemble_bundle(tmp_path)
    except PlatformCliError as exc:
        assert exc.error_code == "bundle_function_not_supported"
        assert exc.exit_code == 2
    else:
        raise AssertionError("function field must fail")
