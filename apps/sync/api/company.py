"""REST-зеркала команд company. Тонкие обвязки над `op_company_*`."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.sync.di import Di
from apps.sync.models.channels import ChannelRead
from apps.sync.models.company_members import CompanyMemberRead
from apps.sync.realtime.operations import (
    CompanyMembersListPayload,
    CompanySharedChannelsListPayload,
    op_company_members_list,
    op_company_shared_channels_list,
)
from core.context import require_context
from core.pagination import OffsetPage

router = APIRouter()


@router.get("/members", response_model=OffsetPage[CompanyMemberRead])
async def list_company_members(
    di: Di,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[CompanyMemberRead]:
    user = require_context().user
    return await op_company_members_list(
        CompanyMembersListPayload(limit=limit, offset=offset),
        user=user,
        di=di,
    )


@router.get(
    "/members/{peer_user_id}/shared-channels", response_model=OffsetPage[ChannelRead]
)
async def list_shared_channels_with_member(
    peer_user_id: str,
    di: Di,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[ChannelRead]:
    user = require_context().user
    return await op_company_shared_channels_list(
        CompanySharedChannelsListPayload(
            peer_user_id=peer_user_id, limit=limit, offset=offset
        ),
        user=user,
        di=di,
    )
