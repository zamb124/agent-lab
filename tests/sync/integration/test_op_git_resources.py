"""op_git_resources_* — upsert + get с реальной БД."""

from __future__ import annotations

import pytest

from apps.sync.models.git import GitProvider, GitResourceKind, GitResourceRefCreate
from apps.sync.realtime.operations import (
    GitResourcesGetPayload,
    GitResourcesUpsertPayload,
    op_git_resources_get,
    op_git_resources_upsert,
)
from core.models.identity_models import User
from core.websocket import WsCommandError


@pytest.mark.asyncio
async def test_op_git_resources_upsert_then_get_roundtrip(
    op_user: User,
    sync_di,
    op_context: None,
    unique_id: str,
) -> None:
    payload = GitResourcesUpsertPayload(
        body=GitResourceRefCreate(
            provider=GitProvider.GITLAB,
            kind=GitResourceKind.MERGE_REQUEST,
            project_key=f"team/proj_{unique_id}",
            external_id="42",
            url=f"https://git.example.com/team/proj_{unique_id}/-/merge_requests/42",
        )
    )
    upserted = await op_git_resources_upsert(payload, user=op_user, di=sync_di)

    fetched = await op_git_resources_get(
        GitResourcesGetPayload(git_ref_id=upserted.git_ref_id),
        user=op_user,
        di=sync_di,
    )
    assert fetched.git_ref_id == upserted.git_ref_id
    assert fetched.url == payload.body.url


@pytest.mark.asyncio
async def test_op_git_resources_upsert_idempotent(
    op_user: User,
    sync_di,
    op_context: None,
    unique_id: str,
) -> None:
    body = GitResourceRefCreate(
        provider=GitProvider.GITHUB,
        kind=GitResourceKind.PULL_REQUEST,
        project_key=f"org/repo_{unique_id}",
        external_id="7",
        url="https://github.example.com/x",
    )
    first = await op_git_resources_upsert(
        GitResourcesUpsertPayload(body=body), user=op_user, di=sync_di
    )
    second_body = GitResourceRefCreate(
        provider=GitProvider.GITHUB,
        kind=GitResourceKind.PULL_REQUEST,
        project_key=f"org/repo_{unique_id}",
        external_id="7",
        url="https://github.example.com/x?refresh",
    )
    second = await op_git_resources_upsert(
        GitResourcesUpsertPayload(body=second_body),
        user=op_user,
        di=sync_di,
    )
    assert first.git_ref_id == second.git_ref_id
    assert second.url.endswith("refresh")


@pytest.mark.asyncio
async def test_op_git_resources_get_not_found_raises(
    op_user: User,
    sync_di,
    op_context: None,
) -> None:
    with pytest.raises(WsCommandError) as exc_info:
        await op_git_resources_get(
            GitResourcesGetPayload(git_ref_id="missing_git_ref_id"),
            user=op_user,
            di=sync_di,
        )
    assert exc_info.value.code == "not_found"
