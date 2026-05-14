"""REST-зеркала команд calls. Тонкие обвязки над `op_calls_*`."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from apps.sync.dependencies import ContainerDep
from apps.sync.models.calls import (
    CallLinkCreate,
    CallLinkInfo,
    CallLinkPatch,
    CallLinkRead,
    CallRead,
    CallScheduledLinkRead,
    GuestJoinRequest,
    JoinResponse,
)
from apps.sync.models.meetings import CallRecordingRead
from apps.sync.realtime.operations import (
    CallsAcceptPayload,
    CallsAdminTransferPayload,
    CallsDeclinePayload,
    CallsGetPayload,
    CallsHangupPayload,
    CallsInvitePayload,
    CallsJoinAcceptPayload,
    CallsJoinInfoPayload,
    CallsLinksListPayload,
    CallsLinksRemovePayload,
    CallsLinksUpdatePayload,
    CallsRecordingsListPayload,
    CallsRecordingStartPayload,
    CallsRecordingStopPayload,
    CallsSignalPayload,
    CallsTokenPayload,
    CallsTurnCredentialsPayload,
    op_calls_accept,
    op_calls_admin_transfer,
    op_calls_decline,
    op_calls_get,
    op_calls_hangup,
    op_calls_invite,
    op_calls_join_accept,
    op_calls_join_info,
    op_calls_links_create,
    op_calls_links_list,
    op_calls_links_remove,
    op_calls_links_update,
    op_calls_recording_start,
    op_calls_recording_stop,
    op_calls_recordings_list,
    op_calls_signal,
    op_calls_token,
    op_calls_turn_credentials,
)
from core.calls.models import TurnCredentials
from core.context import get_context
from core.pagination import OffsetPage

router = APIRouter()


class _CallTransferAdminBody(BaseModel):
    target_user_id: str


class _CallSignalBody(BaseModel):
    target_user_id: str
    signal_type: str
    data: dict


@router.get("/turn-credentials", response_model=TurnCredentials)
async def get_turn_credentials(container: ContainerDep) -> TurnCredentials:
    user = get_context().user
    return await op_calls_turn_credentials(
        CallsTurnCredentialsPayload(), user=user, container=container
    )


@router.post("/links", status_code=201, response_model=CallLinkRead)
async def create_call_link(body: CallLinkCreate, container: ContainerDep) -> CallLinkRead:
    user = get_context().user
    return await op_calls_links_create(body, user=user, container=container)


@router.get("/links/scheduled", response_model=OffsetPage[CallScheduledLinkRead])
async def list_scheduled_call_links(
    start_at: datetime,
    end_at: datetime,
    container: ContainerDep,
    channel_id: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> OffsetPage[CallScheduledLinkRead]:
    user = get_context().user
    result = await op_calls_links_list(
        CallsLinksListPayload(
            start_at=start_at,
            end_at=end_at,
            channel_id=channel_id,
            limit=limit,
            offset=offset,
        ),
        user=user,
        container=container,
    )
    return OffsetPage[CallScheduledLinkRead](
        items=result.items, total=result.total, limit=result.limit, offset=result.offset
    )


@router.patch("/links/{link_token}", response_model=CallLinkRead)
async def patch_call_link(
    link_token: str,
    body: CallLinkPatch,
    container: ContainerDep,
) -> CallLinkRead:
    user = get_context().user
    return await op_calls_links_update(
        CallsLinksUpdatePayload(link_token=link_token, body=body),
        user=user,
        container=container,
    )


@router.delete("/links/{link_token}", status_code=204)
async def delete_call_link(link_token: str, container: ContainerDep) -> None:
    user = get_context().user
    await op_calls_links_remove(
        CallsLinksRemovePayload(link_token=link_token),
        user=user,
        container=container,
    )


@router.get("/{call_id}", response_model=CallRead)
async def get_call(call_id: str, container: ContainerDep) -> CallRead:
    user = get_context().user
    return await op_calls_get(
        CallsGetPayload(call_id=call_id), user=user, container=container
    )


@router.get("/{call_id}/recordings", response_model=list[CallRecordingRead])
async def list_call_recordings(
    call_id: str, container: ContainerDep
) -> list[CallRecordingRead]:
    user = get_context().user
    result = await op_calls_recordings_list(
        CallsRecordingsListPayload(call_id=call_id),
        user=user,
        container=container,
    )
    return result.items


@router.get("/{call_id}/token")
async def get_livekit_token(call_id: str, container: ContainerDep) -> dict[str, str]:
    user = get_context().user
    result = await op_calls_token(
        CallsTokenPayload(call_id=call_id), user=user, container=container
    )
    return {"token": result.token, "livekit_url": result.livekit_url}


@router.get("/join/{link_token}", response_model=CallLinkInfo)
async def get_link_info(link_token: str, container: ContainerDep) -> CallLinkInfo:
    user = get_context().user
    return await op_calls_join_info(
        CallsJoinInfoPayload(link_token=link_token),
        user=user,
        container=container,
    )


@router.post("/join/{link_token}", response_model=JoinResponse)
async def join_via_link(
    link_token: str,
    container: ContainerDep,
    body: Optional[GuestJoinRequest] = None,
) -> JoinResponse:
    user = get_context().user
    return await op_calls_join_accept(
        CallsJoinAcceptPayload(link_token=link_token, body=body),
        user=user,
        container=container,
    )


@router.post("/{call_id}/invite", response_model=CallRead)
async def invite_call(container: ContainerDep, call_id: str, body: dict) -> CallRead:
    _ = call_id
    channel_id = body.get("channel_id")
    if not isinstance(channel_id, str) or channel_id == "":
        from core.websocket import WsCommandError

        raise WsCommandError("ws_invalid_payload", "channel_id required (non-empty string)")
    user = get_context().user
    return await op_calls_invite(
        CallsInvitePayload(channel_id=channel_id), user=user, container=container
    )


@router.post("/{call_id}/accept", response_model=CallRead)
async def accept_call(container: ContainerDep, call_id: str) -> CallRead:
    user = get_context().user
    return await op_calls_accept(
        CallsAcceptPayload(call_id=call_id), user=user, container=container
    )


@router.post("/{call_id}/decline", status_code=204)
async def decline_call(container: ContainerDep, call_id: str) -> None:
    user = get_context().user
    await op_calls_decline(
        CallsDeclinePayload(call_id=call_id), user=user, container=container
    )


@router.post("/{call_id}/hangup", response_model=CallRead)
async def hangup_call(container: ContainerDep, call_id: str) -> CallRead:
    user = get_context().user
    return await op_calls_hangup(
        CallsHangupPayload(call_id=call_id), user=user, container=container
    )


@router.post("/{call_id}/recording/start", response_model=CallRecordingRead)
async def start_call_recording(
    container: ContainerDep, call_id: str
) -> CallRecordingRead:
    user = get_context().user
    return await op_calls_recording_start(
        CallsRecordingStartPayload(call_id=call_id),
        user=user,
        container=container,
    )


@router.post("/{call_id}/recording/stop", response_model=CallRecordingRead)
async def stop_call_recording(
    container: ContainerDep, call_id: str
) -> CallRecordingRead:
    user = get_context().user
    return await op_calls_recording_stop(
        CallsRecordingStopPayload(call_id=call_id),
        user=user,
        container=container,
    )


@router.post("/{call_id}/admin/transfer", response_model=CallRead)
async def transfer_call_admin(
    container: ContainerDep, call_id: str, body: _CallTransferAdminBody
) -> CallRead:
    user = get_context().user
    return await op_calls_admin_transfer(
        CallsAdminTransferPayload(
            call_id=call_id, target_user_id=body.target_user_id
        ),
        user=user,
        container=container,
    )


@router.post("/{call_id}/signal", status_code=204)
async def signal_call(
    container: ContainerDep, call_id: str, body: _CallSignalBody
) -> None:
    user = get_context().user
    await op_calls_signal(
        CallsSignalPayload(
            call_id=call_id,
            target_user_id=body.target_user_id,
            signal_type=body.signal_type,
            data=body.data,
        ),
        user=user,
        container=container,
    )
