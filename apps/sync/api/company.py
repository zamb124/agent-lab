"""REST-зеркала команд company. Тонкие обвязки над `op_company_*`."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.sync.dependencies import ContainerDep
from apps.sync.models.channels import ChannelRead
from apps.sync.models.company_members import CompanyMemberRead
from apps.sync.realtime.context import require_current_user
from apps.sync.realtime.operations import (
    CompanyMembersListPayload,
    CompanySharedChannelsListPayload,
    op_company_members_list,
    op_company_shared_channels_list,
)
from core.pagination import OffsetPage

router = APIRouter()


@router.get("/members", response_model=OffsetPage[CompanyMemberRead])
async def list_company_members(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[CompanyMemberRead]:
    user = require_current_user()
    result = await op_company_members_list(
        CompanyMembersListPayload(limit=limit, offset=offset),
        user=user,
        container=container,
    )
    return OffsetPage[CompanyMemberRead](
        items=result.items, total=result.total, limit=result.limit, offset=result.offset
    )


@router.get(
    "/members/{peer_user_id}/shared-channels", response_model=OffsetPage[ChannelRead]
)
async def list_shared_channels_with_member(
    peer_user_id: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[ChannelRead]:
    user = require_current_user()
    result = await op_company_shared_channels_list(
        CompanySharedChannelsListPayload(
            peer_user_id=peer_user_id, limit=limit, offset=offset
        ),
        user=user,
        container=container,
    )
    return OffsetPage[ChannelRead](
        items=result.items, total=result.total, limit=result.limit, offset=result.offset
    )
