"""Тесты GitResourceRefRepository."""

from __future__ import annotations

import pytest

from apps.sync.db.models import SyncGitResourceRef
from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository


@pytest.mark.asyncio
async def test_git_ref_create_get(
    git_ref_repo: GitResourceRefRepository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    entity = SyncGitResourceRef(
        git_ref_id="gitlab:repo:acme:42",
        company_id=company_id,
        provider="gitlab",
        kind="repo",
        project_key="acme",
        external_id="42",
        url="https://gitlab.example/acme/42",
        extra={"branch": "main"},
    )
    await git_ref_repo.create(entity)
    loaded = await git_ref_repo.get("gitlab:repo:acme:42")
    assert loaded is not None
    assert loaded.company_id == company_id
    assert loaded.url == "https://gitlab.example/acme/42"


@pytest.mark.asyncio
async def test_git_ref_company_isolation(
    git_ref_repo: GitResourceRefRepository,
    sync_db_clean: None,
    company_id: str,
) -> None:
    await git_ref_repo.create(
        SyncGitResourceRef(
            git_ref_id="gitlab:repo:x:1",
            company_id=company_id,
            provider="gitlab",
            kind="repo",
            project_key="x",
            external_id="1",
            url="https://x",
            extra={},
        )
    )
    await git_ref_repo.create(
        SyncGitResourceRef(
            git_ref_id="gitlab:repo:y:2",
            company_id="other_co",
            provider="gitlab",
            kind="repo",
            project_key="y",
            external_id="2",
            url="https://y",
            extra={},
        )
    )
    rows = await git_ref_repo.list_all(company_id=company_id)
    ids = {r.git_ref_id for r in rows}
    assert ids == {"gitlab:repo:x:1"}
