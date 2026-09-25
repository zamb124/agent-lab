"""Обратные ссылки: тонкая REST-обвязка того же `op_backlinks_list`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.wiki.di import Di
from apps.wiki.models.domain import WikiBacklink, WikiLinkTargetKind
from apps.wiki.realtime.operations import WikiBacklinksPayload, op_backlinks_list
from core.context import require_context
from core.pagination import ListResponse

router = APIRouter(prefix="/backlinks", tags=["wiki-backlinks"])


@router.get("", response_model=ListResponse[WikiBacklink])
async def list_backlinks(
    di: Di,
    target_kind: Annotated[WikiLinkTargetKind, Query()],
    target_id: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ListResponse[WikiBacklink]:
    return await op_backlinks_list(
        WikiBacklinksPayload(
            target_kind=target_kind, target_id=target_id, limit=limit
        ),
        user=require_context().user,
        di=di,
    )
