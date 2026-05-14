import pytest

from apps.flows.src.services.bundle_node_repair import (
    _bundle_top_level_nodes,
    _registry_flow_to_bundle,
    repair_effective_nodes_from_bundle,
    repair_node_map_with_canonical_top_level,
)


@pytest.fixture(autouse=True)
def clear_bundle_caches():
    _registry_flow_to_bundle.cache_clear()
    _bundle_top_level_nodes.cache_clear()
    yield
    _registry_flow_to_bundle.cache_clear()
    _bundle_top_level_nodes.cache_clear()


def test_repair_merges_canonical_with_pos() -> None:
    canonical = {
        "formatter": {
            "type": "code",
            "code": "async def run(s): return s",
        }
    }
    broken = {"formatter": {"pos_x": 10, "pos_y": 20}}
    out = repair_node_map_with_canonical_top_level(broken, canonical)
    assert out["formatter"]["type"] == "code"
    assert "async def run" in out["formatter"]["code"]
    assert out["formatter"]["pos_x"] == 10
    assert out["formatter"]["pos_y"] == 20


def test_repair_example_graph_formatter_from_disk() -> None:
    nodes = {"formatter": {"pos_x": 1, "pos_y": 2}}
    out = repair_effective_nodes_from_bundle("example_graph", "file", nodes)
    assert out["formatter"]["type"] == "code"
    assert "format_response" in out["formatter"]["code"]


def test_repair_skips_manual_source() -> None:
    nodes = {"formatter": {"pos_x": 1}}
    out = repair_effective_nodes_from_bundle("example_graph", "manual", nodes)
    assert out == nodes
