"""Запись состояния публичной ссылки Документов."""

from __future__ import annotations

import pytest

from apps.office.models.link import DocumentLink


@pytest.mark.asyncio
async def test_update_enabled_token_hash_and_permission_persists_fields(
    office_di,
    unique_id: str,
) -> None:
    _ = office_di
    target_id = f"file-{unique_id}"
    created = await DocumentLink.ensure(
        company_id=f"co-{unique_id}",
        target_kind="file",
        target_id=target_id,
        created_by_user_id="user-1",
    )
    updated = await DocumentLink.update_enabled_token_hash_and_permission(
        created,
        enabled=True,
        token_hash=f"hash-{unique_id}",
        permission="editor",
    )
    assert updated.enabled is True
    assert updated.token_hash == f"hash-{unique_id}"
    assert updated.permission == "editor"
    loaded = await DocumentLink.for_target("file", target_id)
    assert loaded is not None
    assert loaded.enabled is True
    assert loaded.token_hash == f"hash-{unique_id}"
    assert loaded.permission == "editor"
    cleared = await DocumentLink.update_enabled_token_hash_and_permission(
        loaded,
        enabled=False,
        token_hash=None,
        permission="viewer",
    )
    assert cleared.enabled is False
    assert cleared.token_hash is None
    assert cleared.permission == "viewer"
