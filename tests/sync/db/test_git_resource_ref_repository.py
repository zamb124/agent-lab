"""Git-ресурс Sync: запись и чтение по компании."""

from __future__ import annotations

import pytest

from apps.sync.models.git import GitResourceRef


@pytest.mark.asyncio
async def test_git_ref_create_get(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    _ = sync_db_clean
    gid = f"{unique_id}_gitlab:repo:acme:42"
    entity = GitResourceRef(
        git_ref_id=gid,
        company_id=company_id,
        provider="gitlab",
        kind="repo",
        project_key="acme",
        external_id="42",
        url="https://gitlab.example/acme/42",
        extra={"branch": "main"},
    )
    inserted = await GitResourceRef.set(entity)
    assert inserted is True
    loaded = await GitResourceRef.get(gid)
    assert loaded is not None
    assert loaded.company_id == company_id
    assert loaded.url == "https://gitlab.example/acme/42"
    entity.url = "https://gitlab.example/acme/42/updated"
    updated = await GitResourceRef.set(entity)
    assert updated is True
    reloaded = await GitResourceRef.get(gid)
    assert reloaded is not None
    assert reloaded.url == entity.url


@pytest.mark.asyncio
async def test_git_ref_company_isolation(
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    _ = sync_db_clean
    g1 = f"{unique_id}_gitlab:repo:x:1"
    g2 = f"{unique_id}_gitlab:repo:y:2"
    other_co = f"{unique_id}_other_co"
    _ = await GitResourceRef.set(
        GitResourceRef(
            git_ref_id=g1,
            company_id=company_id,
            provider="gitlab",
            kind="repo",
            project_key="x",
            external_id="1",
            url="https://x",
            extra={},
        )
    )
    _ = await GitResourceRef.set(
        GitResourceRef(
            git_ref_id=g2,
            company_id=other_co,
            provider="gitlab",
            kind="repo",
            project_key="y",
            external_id="2",
            url="https://y",
            extra={},
        )
    )
    rows = await GitResourceRef.objects.filter(company_id=company_id).limit(1000).all()
    ids = {row.git_ref_id for row in rows}
    assert ids == {g1}
