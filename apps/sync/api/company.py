"""Участники компании — для списка «Личные» в Sync UI."""

import asyncio

from fastapi import APIRouter, HTTPException, Query

from core.config import get_settings
from core.pagination import OffsetPage

from apps.sync.channel_read_helpers import channel_read_from_entity
from apps.sync.dependencies import ContainerDep
from apps.sync.models.channels import ChannelRead
from apps.sync.models.company_members import CompanyMemberRead
from apps.sync.ws_presence import batch_peer_presence
from core.context import get_context

router = APIRouter()


@router.get("/members", response_model=OffsetPage[CompanyMemberRead])
async def list_company_members(
    container: ContainerDep,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> OffsetPage[CompanyMemberRead]:
    context = get_context()
    company_id = context.active_company.company_id
    viewer_id = context.user.user_id
    company = await container.company_repository.get(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Компания не найдена.")

    all_member_uids = [uid for uid in company.members if uid != viewer_id]
    total = len(all_member_uids)
    member_uids = all_member_uids[offset : offset + limit]

    settings = get_settings()
    redis_url = settings.database.redis_url
    if not redis_url:
        raise HTTPException(status_code=500, detail="database.redis_url не задан.")

    presence_map, users_by_id = await asyncio.gather(
        batch_peer_presence(redis_url, member_uids),
        container.user_repository.get_many(member_uids),
    )

    out: list[CompanyMemberRead] = []
    for uid in member_uids:
        roles_raw = company.members[uid]
        user = users_by_id.get(uid)
        if user is None:
            raise HTTPException(
                status_code=500,
                detail=f"Участник {uid} указан в компании, но пользователь не найден.",
            )
        roles = list(roles_raw) if isinstance(roles_raw, list) else [roles_raw]
        pr = presence_map[uid]
        out.append(
            CompanyMemberRead(
                user_id=uid,
                name=user.name,
                roles=roles,
                avatar_url=user.avatar_url,
                is_online=pr.is_online,
                last_seen_at=pr.last_seen_at,
            )
        )
    out.sort(key=lambda m: m.name.casefold())
    return OffsetPage[CompanyMemberRead](items=out, total=total, limit=limit, offset=offset)


@router.get("/members/{peer_user_id}/shared-channels", response_model=OffsetPage[ChannelRead])
async def list_shared_channels_with_member(
    peer_user_id: str,
    container: ContainerDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OffsetPage[ChannelRead]:
    """Каналы, где есть и текущий пользователь, и указанный участник компании (как в сайдбаре)."""
    context = get_context()
    company_id = context.active_company.company_id
    viewer_id = context.user.user_id
    company = await container.company_repository.get(company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Компания не найдена.")
    if peer_user_id not in company.members:
        raise HTTPException(status_code=404, detail="Пользователь не в компании.")

    if peer_user_id == viewer_id:
        channels = await container.channel_repository.list_for_user(
            viewer_id,
            space_id=None,
            limit=limit,
            offset=offset,
            company_id=company_id,
        )
    else:
        channels = await container.channel_repository.list_channels_where_both_members(
            viewer_id,
            peer_user_id,
            limit=limit,
            offset=offset,
            company_id=company_id,
        )

    channel_ids = [c.channel_id for c in channels]
    summaries = await container.message_repository.channel_lane_summaries_batch(
        company_id=company_id,
        channel_ids=channel_ids,
        viewer_user_id=viewer_id,
    )
    out: list[ChannelRead] = []
    for c in channels:
        summ = summaries[c.channel_id]
        out.append(
            await channel_read_from_entity(
                c,
                viewer_user_id=viewer_id,
                channel_repository=container.channel_repository,
                user_repository=container.user_repository,
                company_id=company_id,
                lane_summary=summ,
            )
        )
    return OffsetPage[ChannelRead](items=out, total=len(out), limit=limit, offset=offset)
