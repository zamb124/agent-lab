"""EmbedConfig хранится в platform_shared и читается по company_id."""

from __future__ import annotations

import pytest

from core.models.embed_models import EmbedConfig, EmbedStatus


def _config(embed_id: str, company_id: str, name: str) -> EmbedConfig:
    return EmbedConfig(
        embed_id=embed_id,
        company_id=company_id,
        name=name,
        flow_id="embed_flow_fixture",
        status=EmbedStatus.ACTIVE,
        created_by="test_user",
    )


@pytest.mark.asyncio
async def test_embed_config_set_get_and_delete(unique_id: str) -> None:
    embed_id = f"embed_{unique_id}"
    company_id = f"co_{unique_id}"
    await EmbedConfig.set(_config(embed_id, company_id, "Test Widget"))

    loaded = await EmbedConfig.get(embed_id)
    assert loaded is not None
    assert loaded.name == "Test Widget"
    assert loaded.flow_id == "embed_flow_fixture"
    assert loaded.company_id == company_id

    loaded.name = "Renamed"
    await EmbedConfig.set(loaded)
    updated = await EmbedConfig.embed_for_company(embed_id, company_id)
    assert updated is not None
    assert updated.name == "Renamed"

    assert await EmbedConfig.delete_by_id(embed_id) is True
    assert await EmbedConfig.get(embed_id) is None


@pytest.mark.asyncio
async def test_embed_config_list_is_company_scoped(unique_id: str) -> None:
    company_a = f"co_a_{unique_id}"
    company_b = f"co_b_{unique_id}"
    id_a = f"embed_a_{unique_id}"
    id_b = f"embed_b_{unique_id}"
    await EmbedConfig.set(_config(id_a, company_a, "A"))
    await EmbedConfig.set(_config(id_b, company_b, "B"))
    try:
        listed = await EmbedConfig.list_unordered_window_for_company(company_a, limit=100, offset=0)
        ids = {item.embed_id for item in listed}
        assert id_a in ids
        assert id_b not in ids
    finally:
        _ = await EmbedConfig.delete_by_id(id_a)
        _ = await EmbedConfig.delete_by_id(id_b)
