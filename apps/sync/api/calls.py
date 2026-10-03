"""REST-зеркала команд calls. Тонкие обвязки над `op_calls_*`."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from apps.sync.di import Di
from apps.sync.models.calls import (
    CallLinkCreate,
    CallLinkInfo,
    CallLinkPatch,
    CallLinkRead,
    CallRead,
    CallsAcceptPayload,
    CallScheduledLinkRead,
    CallsDeclinePayload,
    CallsHangupPayload,
    CallsInvitePayload,
    CallsJoinAcceptPayload,
    CallsJoinInfoPayload,
    CallsLinksListPayload,
    CallsLinksRemovePayload,
    CallsLinksUpdatePayload,
    CallsSignalPayload,
    GuestJoinRequest,
    JoinResponse,
)
from apps.sync.models.meetings import CallRecordingRead
from apps.sync.realtime.operations import (
    CallsAdminTransferPayload,
    CallsGetPayload,
    CallsRecordingsListPayload,
    CallsRecordingStartPayload,
    CallsRecordingStopPayload,
    CallsTokenPayload,
    CallsTokenResult,
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
from core.context import require_context
from core.pagination import ListResponse, OffsetPage
from core.websocket import WsCommandError

router = APIRouter()


@router.get("/turn-credentials", response_model=TurnCredentials)
async def get_turn_credentials(di: Di) -> TurnCredentials:
    user = require_context().user
    return await op_calls_turn_credentials(
        CallsTurnCredentialsPayload(), user=user, di=di
    )


@router.post("/links", status_code=201, response_model=CallLinkRead)
async def create_call_link(body: CallLinkCreate, di: Di) -> CallLinkRead:
    user = require_context().user
    return await op_calls_links_create(body, user=user, di=di)


@router.get("/links/scheduled", response_model=OffsetPage[CallScheduledLinkRead])
async def list_scheduled_call_links(
    start_at: datetime,
    end_at: datetime,
    di: Di,
    channel_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[CallScheduledLinkRead]:
    user = require_context().user
    return await op_calls_links_list(
        CallsLinksListPayload(
            start_at=start_at,
            end_at=end_at,
            channel_id=channel_id,
            limit=limit,
            offset=offset,
        ),
        user=user,
        di=di,
    )


@router.patch("/links/{link_token}", response_model=CallLinkRead)
async def patch_call_link(
    link_token: str,
    body: CallLinkPatch,
    di: Di,
) -> CallLinkRead:
    user = require_context().user
    return await op_calls_links_update(
        CallsLinksUpdatePayload(link_token=link_token, body=body),
        user=user,
        di=di,
    )


@router.delete("/links/{link_token}", status_code=204)
async def delete_call_link(link_token: str, di: Di) -> None:
    user = require_context().user
    await op_calls_links_remove(
        CallsLinksRemovePayload(link_token=link_token),
        user=user,
        di=di,
    )


@router.get("/{call_id}", response_model=CallRead)
async def get_call(call_id: str, di: Di) -> CallRead:
    user = require_context().user
    return await op_calls_get(
        CallsGetPayload(call_id=call_id), user=user, di=di
    )


@router.get("/{call_id}/recordings", response_model=ListResponse[CallRecordingRead])
async def list_call_recordings(
    call_id: str, di: Di
) -> ListResponse[CallRecordingRead]:
    user = require_context().user
    return await op_calls_recordings_list(
        CallsRecordingsListPayload(call_id=call_id),
        user=user,
        di=di,
    )


@router.get("/{call_id}/token", response_model=CallsTokenResult)
async def get_livekit_token(call_id: str, di: Di) -> CallsTokenResult:
    user = require_context().user
    return await op_calls_token(
        CallsTokenPayload(call_id=call_id), user=user, di=di
    )


@router.get("/join/{link_token}", response_model=CallLinkInfo)
async def get_link_info(link_token: str, di: Di) -> CallLinkInfo:
    user = require_context().user
    return await op_calls_join_info(
        CallsJoinInfoPayload(link_token=link_token),
        user=user,
        di=di,
    )


@router.post("/join/{link_token}", response_model=JoinResponse)
async def join_via_link(
    link_token: str,
    di: Di,
    body: GuestJoinRequest | None = None,
) -> JoinResponse:
    user = require_context().user
    return await op_calls_join_accept(
        CallsJoinAcceptPayload(link_token=link_token, body=body),
        user=user,
        di=di,
    )


@router.post("/{call_id}/invite", response_model=CallRead)
async def invite_call(di: Di, call_id: str, body: CallsInvitePayload) -> CallRead:
    _ = call_id
    user = require_context().user
    return await op_calls_invite(body, user=user, di=di)


@router.post("/{call_id}/accept", response_model=CallRead)
async def accept_call(di: Di, call_id: str) -> CallRead:
    user = require_context().user
    return await op_calls_accept(
        CallsAcceptPayload(call_id=call_id), user=user, di=di
    )


@router.post("/{call_id}/decline", response_model=CallRead)
async def decline_call(di: Di, call_id: str) -> CallRead:
    user = require_context().user
    return await op_calls_decline(
        CallsDeclinePayload(call_id=call_id), user=user, di=di
    )


@router.post("/{call_id}/hangup", response_model=CallRead)
async def hangup_call(di: Di, call_id: str) -> CallRead:
    user = require_context().user
    return await op_calls_hangup(
        CallsHangupPayload(call_id=call_id), user=user, di=di
    )


@router.post("/{call_id}/recording/start", response_model=CallRecordingRead)
async def start_call_recording(
    di: Di, call_id: str
) -> CallRecordingRead:
    user = require_context().user
    return await op_calls_recording_start(
        CallsRecordingStartPayload(call_id=call_id),
        user=user,
        di=di,
    )


@router.post("/{call_id}/recording/stop", response_model=CallRecordingRead)
async def stop_call_recording(
    di: Di, call_id: str
) -> CallRecordingRead:
    user = require_context().user
    return await op_calls_recording_stop(
        CallsRecordingStopPayload(call_id=call_id),
        user=user,
        di=di,
    )


@router.post("/{call_id}/admin/transfer", response_model=CallRead)
async def transfer_call_admin(
    di: Di, call_id: str, body: CallsAdminTransferPayload
) -> CallRead:
    if body.call_id != call_id:
        raise WsCommandError("ws_invalid_payload", "call_id mismatch", error_code='ws_invalid_payload')
    user = require_context().user
    return await op_calls_admin_transfer(body, user=user, di=di)


@router.post("/{call_id}/signal", status_code=204)
async def signal_call(
    di: Di, call_id: str, body: CallsSignalPayload
) -> None:
    if body.call_id != call_id:
        raise WsCommandError("ws_invalid_payload", "call_id mismatch", error_code='ws_invalid_payload')
    user = require_context().user
    await op_calls_signal(body, user=user, di=di)
