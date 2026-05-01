"""
Тесты материализации store_card_image при сборке FlowConfig из bundle (S3 + FileRecord).
"""

from pathlib import Path

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.services.flows_loader import FlowsLoader, load_tools_to_db


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


@pytest.mark.asyncio
async def test_landing_demo_bundles_store_card_image_in_storage(app) -> None:
    """Демо-лендинг bundles: JPEG рядом с flow.json → store_card_image_url и запись файла в БД/S3."""
    _ = app
    container = get_container()
    await load_tools_to_db(container.tool_repository)

    bundles_dir = _repo_root() / "apps" / "flows" / "bundles"
    registry_path = _repo_root() / "apps" / "flows" / "registry.yaml"

    loader = FlowsLoader(
        bundles_dir=bundles_dir,
        flow_repository=container.flow_repository,
        node_repository=container.node_repository,
        tool_repository=container.tool_repository,
        registry_path=registry_path,
    )
    loader._target_company_id = "system"
    await loader._load_tools_cache()
    await loader._load_nodes_cache()

    prefix = "/flows/api/v1/files/download/"
    demo_ids = ("lawyer", "doctor", "psy", "coach", "tutor")

    for bundle_id in demo_ids:
        jpg = bundles_dir / bundle_id / f"{bundle_id}.jpg"
        assert jpg.is_file(), f"ожидается изображение: {jpg}"

        flow_cfg = await loader.build_flow_bundle_config(bundle_id)
        assert flow_cfg is not None
        url = flow_cfg.store_card_image_url
        assert isinstance(url, str) and len(url) > 0
        assert prefix in url
        assert url.startswith(prefix)

        file_id = url.rstrip("/").split("/")[-1]
        assert file_id.startswith("file_")
        record = await container.file_processor.get_file_record(file_id)
        assert record is not None
        assert record.content_type.startswith("image/")
        assert record.is_public is True
        assert record.file_size > 0


@pytest.mark.asyncio
async def test_resolve_store_card_image_https_passthrough(app) -> None:
    """Строка store_card_image с https:// не проходит повторную загрузку."""
    _ = app
    container = get_container()
    bundles_dir = _repo_root() / "apps" / "flows" / "bundles"
    registry_path = _repo_root() / "apps" / "flows" / "registry.yaml"
    loader = FlowsLoader(
        bundles_dir=bundles_dir,
        flow_repository=container.flow_repository,
        node_repository=container.node_repository,
        tool_repository=container.tool_repository,
        registry_path=registry_path,
    )
    loader._target_company_id = "system"

    expected = "https://example.invalid/demo/card.png"
    url_out = await loader._resolve_store_card_image_url(
        {"store_card_image": expected},
        bundles_dir / "lawyer",
    )
    assert url_out == expected

    url_only = await loader._resolve_store_card_image_url(
        {"store_card_image_url": "https://cdn.example/only.png"},
        bundles_dir / "lawyer",
    )
    assert url_only == "https://cdn.example/only.png"
