"""Unit-тесты depends_on_flow_ids для platform bundle flows."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.flows.src.services.flows_loader import FlowsLoader


@pytest.fixture
def bundles_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "apps" / "flows" / "bundles"


@pytest.fixture
def loader(bundles_dir: Path, container) -> FlowsLoader:
    return FlowsLoader(
        bundles_dir=bundles_dir,
        flow_repository=container.flow_repository,
        node_repository=container.node_repository,
        tool_repository=container.tool_repository,
        registry_path=bundles_dir.parent / "registry.yaml",
    )


def test_expand_handoff_demo_parent_puts_child_first(loader: FlowsLoader) -> None:
    ordered = loader._expand_bundle_ids_with_dependencies(["handoff_demo_parent"])
    assert ordered.index("handoff_demo_child") < ordered.index("handoff_demo_parent")


def test_read_depends_on_flow_ids_from_handoff_parent(loader: FlowsLoader, bundles_dir: Path) -> None:
    deps = loader._read_bundle_depends_on_flow_ids(bundles_dir / "handoff_demo_parent")
    assert deps == ["handoff_demo_child"]


def test_expand_detects_cycle(loader: FlowsLoader, tmp_path: Path, container) -> None:
    parent_dir = tmp_path / "cycle_parent"
    child_dir = tmp_path / "cycle_child"
    parent_dir.mkdir()
    child_dir.mkdir()
    (parent_dir / "flow.json").write_text(
        '{"flow_id":"cycle_parent","depends_on_flow_ids":["cycle_child"]}',
        encoding="utf-8",
    )
    (child_dir / "flow.json").write_text(
        '{"flow_id":"cycle_child","depends_on_flow_ids":["cycle_parent"]}',
        encoding="utf-8",
    )
    cycle_loader = FlowsLoader(
        bundles_dir=tmp_path,
        flow_repository=container.flow_repository,
        node_repository=container.node_repository,
        tool_repository=container.tool_repository,
        registry_path=tmp_path / "registry.yaml",
    )
    with pytest.raises(ValueError, match="Cycle in depends_on_flow_ids"):
        cycle_loader._expand_bundle_ids_with_dependencies(["cycle_parent"])
