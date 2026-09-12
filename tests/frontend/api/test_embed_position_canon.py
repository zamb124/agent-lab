"""EmbedConfig: ``presentation`` и ``position`` — независимые типизированные поля.

``presentation`` выбирает drawer или полноэкранную страницу, ``position`` — только угол
launcher-кнопки. Проверяются API create/patch, сниппет встраивания, public page-session
и правило миграции ``shared_0035`` для legacy ``position=fullscreen``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from httpx import AsyncClient

from core.types import JsonObject

MIGRATION_PATH = Path("migrations/shared/versions/20260911_0035_embed_position_canon.py")


def _load_migration() -> ModuleType:
    name = "_embed_position_canon_migration"
    loaded = sys.modules.get(name)
    if loaded is not None:
        return loaded
    spec = importlib.util.spec_from_file_location(name, MIGRATION_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load migration {MIGRATION_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


async def _create(frontend_client: AsyncClient, auth_headers: dict[str, str], body: JsonObject) -> JsonObject:
    response = await frontend_client.post("/frontend/api/embed/configs", headers=auth_headers, json=body)
    assert response.status_code == 200, response.text
    created = response.json()
    assert isinstance(created, dict)
    return created


@pytest.mark.asyncio
async def test_position_and_presentation_are_validated_independently(
    frontend_client: AsyncClient, embed_test_auth
) -> None:
    auth_headers, flow_id, _, _ = embed_test_auth
    for body in (
        {"name": "legacy", "flow_id": flow_id, "position": "fullscreen"},
        {"name": "bad-corner", "flow_id": flow_id, "position": "top-left"},
        {"name": "bad-presentation", "flow_id": flow_id, "presentation": "modal"},
    ):
        response = await frontend_client.post("/frontend/api/embed/configs", headers=auth_headers, json=body)
        assert response.status_code == 422, response.text

    created = await _create(frontend_client, auth_headers, {"name": "defaults", "flow_id": flow_id})
    embed_id = created["embed_id"]
    try:
        assert created["presentation"] == "drawer"
        assert created["position"] == "bottom-right"
        assert created["show_launcher"] is True
    finally:
        _ = await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_patch_position_and_presentation_reach_the_snippet(
    frontend_client: AsyncClient, embed_test_auth
) -> None:
    auth_headers, flow_id, _, _ = embed_test_auth
    created = await _create(frontend_client, auth_headers, {"name": "patchable", "flow_id": flow_id})
    embed_id = created["embed_id"]
    try:
        patched = await frontend_client.patch(
            f"/frontend/api/embed/configs/{embed_id}",
            headers=auth_headers,
            json={"position": "bottom-left", "presentation": "page", "show_launcher": False},
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["position"] == "bottom-left"
        assert patched.json()["presentation"] == "page"
        assert patched.json()["show_launcher"] is False

        fetched = await frontend_client.get(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)
        assert fetched.status_code == 200
        assert (fetched.json()["position"], fetched.json()["presentation"]) == ("bottom-left", "page")

        code = await frontend_client.get(f"/frontend/api/embed/configs/{embed_id}/code", headers=auth_headers)
        assert code.status_code == 200
        html_code = code.json()["html_code"]
        assert 'data-position="bottom-left"' in html_code
        assert 'data-presentation="page"' in html_code
        assert 'data-show-launcher="false"' in html_code
        assert code.json()["presentation"] == "page"

        for body in ({"position": None}, {"presentation": None}):
            rejected = await frontend_client.patch(
                f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers, json=body
            )
            assert rejected.status_code == 400, rejected.text
            assert "не может быть null" in rejected.json()["detail"]
        for body in ({"position": "fullscreen"}, {"presentation": "fullscreen"}):
            rejected = await frontend_client.patch(
                f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers, json=body
            )
            assert rejected.status_code == 422, rejected.text

        unchanged = await frontend_client.get(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)
        assert (unchanged.json()["position"], unchanged.json()["presentation"]) == ("bottom-left", "page")
    finally:
        _ = await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_public_page_session_rejects_foreign_origin_and_disabled_widget(
    frontend_client: AsyncClient, embed_test_auth
) -> None:
    auth_headers, flow_id, _, _ = embed_test_auth
    created = await _create(
        frontend_client, auth_headers, {"name": "page", "flow_id": flow_id, "presentation": "page"}
    )
    embed_id = created["embed_id"]
    origin = str(frontend_client.base_url).rstrip("/")
    try:
        foreign = await frontend_client.post(
            "/frontend/api/public/embed-page/session",
            json={"embed_id": embed_id, "origin": "https://evil.example"},
        )
        assert foreign.status_code == 403
        malformed = await frontend_client.post(
            "/frontend/api/public/embed-page/session",
            json={"embed_id": embed_id, "origin": "not a url"},
        )
        assert malformed.status_code == 400
        empty = await frontend_client.post(
            "/frontend/api/public/embed-page/session",
            json={"embed_id": embed_id, "origin": "  "},
        )
        assert empty.status_code == 400
        unknown = await frontend_client.post(
            "/frontend/api/public/embed-page/session",
            json={"embed_id": f"{embed_id}-missing", "origin": origin},
        )
        assert unknown.status_code == 404

        disabled = await frontend_client.patch(
            f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers, json={"status": "disabled"}
        )
        assert disabled.status_code == 200
        denied = await frontend_client.post(
            "/frontend/api/public/embed-page/session",
            json={"embed_id": embed_id, "origin": origin},
        )
        assert denied.status_code == 403
    finally:
        _ = await frontend_client.delete(f"/frontend/api/embed/configs/{embed_id}", headers=auth_headers)


class TestMigrationRule:
    def test_legacy_fullscreen_becomes_page_presentation(self) -> None:
        migration = _load_migration()
        migrated = migration._canonical_embed_config({"position": "fullscreen", "presentation": "drawer"})  # pyright: ignore[reportPrivateUsage]
        assert migrated == {"position": "bottom-right", "presentation": "page"}
        migrated = migration._canonical_embed_config({"position": " FullScreen "})  # pyright: ignore[reportPrivateUsage]
        assert migrated == {"position": "bottom-right", "presentation": "page"}

    def test_unknown_legacy_corner_falls_back_to_default_corner_without_touching_presentation(self) -> None:
        migration = _load_migration()
        migrated = migration._canonical_embed_config({"position": "top-right", "presentation": "page"})  # pyright: ignore[reportPrivateUsage]
        assert migrated == {"position": "bottom-right", "presentation": "page"}
        kept = migration._canonical_embed_config({"position": "bottom-left"})  # pyright: ignore[reportPrivateUsage]
        assert kept == {"position": "bottom-left"}

    def test_non_string_position_fails_the_migration(self) -> None:
        migration = _load_migration()
        with pytest.raises(ValueError, match="position must be a string"):
            _ = migration._canonical_embed_config({"position": None})  # pyright: ignore[reportPrivateUsage]
        with pytest.raises(RuntimeError, match="cannot be reverted"):
            migration.downgrade()
