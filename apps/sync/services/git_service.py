"""Сценарии Git-ссылок Sync."""

from __future__ import annotations

from apps.sync.events import event_git_resource_upserted
from apps.sync.models.git import (
    GitProvider,
    GitResourceKind,
    GitResourceRef,
    GitResourceRefCreate,
    GitResourceRefRead,
)
from core.events import publish_events
from core.websocket import WsCommandError


class SyncGitService:
    """Запись и чтение Git-ссылки канала."""

    async def upsert(
        self,
        body: GitResourceRefCreate,
        *,
        company_id: str,
    ) -> GitResourceRefRead:
        ref_id = (
            f"{body.provider.value}:{body.kind.value}:{body.project_key}:{body.external_id}"
        )
        extra = body.extra
        if extra is None:
            extra = {}
        entity = GitResourceRef(
            git_ref_id=ref_id,
            company_id=company_id,
            provider=body.provider.value,
            kind=body.kind.value,
            project_key=body.project_key,
            external_id=body.external_id,
            url=body.url,
            extra=extra,
        )
        _ = await GitResourceRef.set(entity)
        ref = GitResourceRefRead(
            git_ref_id=ref_id,
            provider=body.provider,
            kind=body.kind,
            project_key=body.project_key,
            external_id=body.external_id,
            url=body.url,
            extra=extra,
        )
        await publish_events([event_git_resource_upserted(ref, company_id=company_id)])
        return ref

    async def get(self, git_ref_id: str) -> GitResourceRefRead:
        ref = await GitResourceRef.get(git_ref_id)
        if ref is None:
            raise WsCommandError(
                "not_found", "Git resource not found", error_code="not_found"
            )
        return GitResourceRefRead(
            git_ref_id=ref.git_ref_id,
            provider=GitProvider(ref.provider),
            kind=GitResourceKind(ref.kind),
            project_key=ref.project_key,
            external_id=ref.external_id,
            url=ref.url,
            extra=ref.extra,
        )
