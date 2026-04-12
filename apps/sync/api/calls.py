"""REST API для WebRTC звонков."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from core.pagination import OffsetPage
from apps.sync.constants import CHANNEL_TYPE_CALENDAR_MEETING
from apps.sync.dependencies import ContainerDep
from apps.sync.db.models import SyncCall, SyncCallLink, SyncChannel
from apps.sync.models.calls import (
    CallLinkCreate,
    CallLinkInfo,
    CallLinkPatch,
    CallLinkRead,
    CallParticipantRead,
    CallRead,
    CallScheduledLinkRead,
    GuestJoinRequest,
    JoinResponse,
)
from apps.sync.models.meetings import CallRecordingRead
from core.calls.livekit_client import LiveKitClient
from core.calls.models import TurnCredentials
from core.calls.turn import generate_turn_credentials
from core.config import get_settings
from core.context import get_context
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


def _build_call_read(call: "SyncCall", participants: list) -> CallRead:
    return CallRead(
        call_id=call.call_id,
        channel_id=call.channel_id,
        mode=call.mode,
        call_type="video",
        status=call.status,
        livekit_room_name=call.livekit_room_name,
        started_at=call.started_at,
        ended_at=call.ended_at,
        created_at=call.created_at,
        created_by_user_id=call.created_by_user_id,
        participants=[
            CallParticipantRead(
                user_id=p.user_id,
                status=p.status,
                joined_at=p.joined_at,
                left_at=p.left_at,
            )
            for p in participants
        ],
    )


def _livekit_client(settings) -> LiveKitClient:
    return LiveKitClient(
        url=settings.calls.livekit_url,
        api_key=settings.calls.livekit_api_key,
        api_secret=settings.calls.livekit_api_secret,
    )


def _livekit_public_url(settings) -> str:
    """URL для браузера: livekit_public_url если задан, иначе livekit_url."""
    return settings.calls.livekit_public_url or settings.calls.livekit_url


async def _participant_names_for_call(container, call: SyncCall) -> dict[str, str]:
    """Соответствие LiveKit identity (user_id / guest:...) -> имя для оверлея (в т.ч. у гостя по ссылке)."""
    out: dict[str, str] = {}
    member_ids = await container.channel_repository.list_member_user_ids(
        call.channel_id, company_id=call.company_id
    )
    for uid in member_ids:
        user = await container.user_repository.get(uid)
        out[uid] = user.name if user is not None else uid

    for p in await container.call_repository.list_participants(call.call_id):
        uid = p.user_id
        if uid in out:
            continue
        if uid.startswith("guest:"):
            parts = uid.split(":", 2)
            out[uid] = parts[2] if len(parts) >= 3 else "Гость"
        else:
            user = await container.user_repository.get(uid)
            out[uid] = user.name if user is not None else uid

    return out


async def _mint_join_short_url(container, link_token: str, expires_at: datetime) -> str:
    return await container.short_link_service.mint_sync_call_join(link_token, expires_at)


def _ttl_hours_from_schedule(scheduled_end: datetime, now: datetime) -> int:
    delta = scheduled_end - now
    hours = int(delta.total_seconds() / 3600.0) + 2
    return max(1, min(168, hours))


async def _reconcile_calendar_meeting_channel_members(
    *,
    container,
    channel_id: str,
    company_id: str,
    link_creator_user_id: str,
    calendar_member_user_ids: list[str],
) -> None:
    channels = container.channel_repository
    desired_guests = {
        uid for uid in calendar_member_user_ids if uid and uid != link_creator_user_id
    }
    for uid in sorted(desired_guests):
        await channels.add_member_if_missing(channel_id, uid, "member", company_id=company_id)
    current = await channels.list_member_user_ids(channel_id, company_id=company_id)
    desired = {link_creator_user_id} | desired_guests
    for uid in current:
        if uid not in desired:
            await channels.delete_member(channel_id, uid, company_id=company_id)


# ─── Авторизованные эндпоинты ────────────────────────────────────────────────

@router.get("/turn-credentials")
async def get_turn_credentials(container: ContainerDep) -> TurnCredentials:
    """Временные TURN credentials для WebRTC ICE (coturn HMAC-SHA1)."""
    _ = container
    settings = get_settings()
    context = get_context()
    return generate_turn_credentials(
        user_id=context.user.user_id,
        turn_host=settings.calls.turn_host,
        turn_port=settings.calls.turn_port,
        turn_secret=settings.calls.turn_secret,
        ttl=settings.calls.turn_credential_ttl,
    )


@router.post("/links", status_code=201)
async def create_call_link(body: CallLinkCreate, container: ContainerDep) -> CallLinkRead:
    """
    Создаёт постоянную ссылку на звонок.

    По ней может войти любой — зарегистрированный пользователь или гость.
    Звонок создаётся в SFU-режиме при первом входе.

    Если передан calendar_event_id, создаётся канал типа calendar_meeting и ссылка на него.
    """
    context = get_context()
    company_id = context.active_company.company_id
    actor_id = context.user.user_id

    channel_id: str
    attached_call_id: Optional[str] = None
    calendar_title: Optional[str] = None
    cal_start: Optional[datetime] = None
    cal_end: Optional[datetime] = None
    cal_event_id: Optional[str] = None
    ttl_hours = body.ttl_hours

    if body.calendar_event_id:
        dup = await container.call_repository.get_link_by_calendar_event(
            company_id, body.calendar_event_id
        )
        if dup is not None:
            raise HTTPException(
                status_code=409,
                detail="Для этого события календаря уже создана ссылка.",
            )
        channel_id = uuid4().hex
        ch = SyncChannel(
            channel_id=channel_id,
            company_id=company_id,
            space_id=None,
            type=CHANNEL_TYPE_CALENDAR_MEETING,
            name=body.scheduled_title.strip(),
            is_private=False,
            created_at=datetime.now(UTC),
            created_by_user_id=actor_id,
            pinned_message_ids=[],
        )
        await container.channel_repository.create(ch)
        await container.channel_repository.add_member_if_missing(
            channel_id, actor_id, "owner", company_id=company_id
        )
        mids = body.calendar_member_user_ids or []
        for uid in mids:
            if uid == actor_id:
                continue
            await container.channel_repository.add_member_if_missing(
                channel_id, uid, "member", company_id=company_id
            )
        now = datetime.now(UTC)
        ttl_hours = _ttl_hours_from_schedule(body.scheduled_end_at, now)
        expires_at = now + timedelta(hours=ttl_hours)
        calendar_title = body.scheduled_title.strip()
        cal_start = body.scheduled_start_at
        cal_end = body.scheduled_end_at
        cal_event_id = body.calendar_event_id
    else:
        assert body.channel_id is not None
        channel_id = body.channel_id
        if not await container.channel_repository.is_member(
            channel_id, actor_id, company_id=company_id
        ):
            raise HTTPException(status_code=403, detail="Нет доступа к каналу.")

        if body.call_id:
            try:
                existing = await container.call_repository.get_call(body.call_id, company_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            if existing.channel_id != channel_id:
                raise HTTPException(
                    status_code=400,
                    detail="Звонок относится к другому каналу.",
                )
            if existing.status not in ("ringing", "active"):
                raise HTTPException(
                    status_code=400,
                    detail="Ссылка на конференцию доступна только для активного или входящего звонка.",
                )
            if existing.mode != "sfu":
                raise HTTPException(status_code=400, detail="Гостевая ссылка поддерживается только для SFU-звонков.")
            if not existing.livekit_room_name:
                raise HTTPException(status_code=400, detail="У звонка нет LiveKit-комнаты.")
            attached_call_id = existing.call_id
        expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)

    link_token = uuid4().hex
    link = SyncCallLink(
        link_token=link_token,
        channel_id=channel_id,
        company_id=company_id,
        call_id=attached_call_id,
        call_type="video",
        created_by_user_id=actor_id,
        expires_at=expires_at,
        title=calendar_title,
        scheduled_start_at=cal_start,
        scheduled_end_at=cal_end,
        calendar_event_id=cal_event_id,
    )
    await container.call_repository.create_link(link)

    join_url = await _mint_join_short_url(container, link_token, expires_at)

    return CallLinkRead(
        link_token=link_token,
        channel_id=channel_id,
        call_type="video",
        expires_at=expires_at,
        join_url=join_url,
        title=calendar_title,
        scheduled_start_at=cal_start,
        scheduled_end_at=cal_end,
        calendar_event_id=cal_event_id,
    )


@router.get("/links/scheduled", response_model=OffsetPage[CallScheduledLinkRead])
async def list_scheduled_call_links(
    start_at: datetime,
    end_at: datetime,
    container: ContainerDep,
    channel_id: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> OffsetPage[CallScheduledLinkRead]:
    context = get_context()
    company_id = context.active_company.company_id
    user_id = context.user.user_id
    rows = await container.call_repository.list_scheduled_calendar_links_for_user(
        company_id,
        user_id,
        range_start=start_at,
        range_end=end_at,
        channel_id=channel_id,
    )
    out: list[CallScheduledLinkRead] = []
    for row in rows:
        if row.scheduled_start_at is None or row.scheduled_end_at is None:
            continue
        if row.calendar_event_id is None:
            continue
        join_url = await _mint_join_short_url(container, row.link_token, row.expires_at)
        out.append(
            CallScheduledLinkRead(
                link_token=row.link_token,
                channel_id=row.channel_id,
                title=row.title,
                scheduled_start_at=row.scheduled_start_at,
                scheduled_end_at=row.scheduled_end_at,
                calendar_event_id=row.calendar_event_id,
                join_url=join_url,
                expires_at=row.expires_at,
            )
        )
    page = out[offset:offset + limit]
    return OffsetPage[CallScheduledLinkRead](items=page, total=len(out), limit=limit, offset=offset)


@router.patch("/links/{link_token}", response_model=CallLinkRead)
async def patch_call_link(
    link_token: str,
    body: CallLinkPatch,
    container: ContainerDep,
) -> CallLinkRead:
    context = get_context()
    company_id = context.active_company.company_id
    user_id = context.user.user_id
    link = await container.call_repository.get_link_for_company(link_token, company_id)
    if link.calendar_event_id is None:
        raise HTTPException(status_code=400, detail="Патч поддерживается только для календарных ссылок.")
    if not await container.channel_repository.is_member(
        link.channel_id, user_id, company_id=company_id
    ):
        raise HTTPException(status_code=403, detail="Нет доступа к ссылке.")

    new_start = body.scheduled_start_at if body.scheduled_start_at is not None else link.scheduled_start_at
    new_end = body.scheduled_end_at if body.scheduled_end_at is not None else link.scheduled_end_at
    if new_start is None or new_end is None:
        raise HTTPException(status_code=400, detail="У ссылки должны быть границы расписания.")
    if new_start >= new_end:
        raise HTTPException(status_code=400, detail="Некорректный интервал встречи.")

    new_title = body.scheduled_title if body.scheduled_title is not None else link.title
    now = datetime.now(UTC)
    new_expires = now + timedelta(hours=_ttl_hours_from_schedule(new_end, now))

    await container.call_repository.update_calendar_link(
        link_token,
        company_id,
        title=new_title,
        scheduled_start_at=new_start,
        scheduled_end_at=new_end,
        expires_at=new_expires,
    )
    if body.scheduled_title is not None:
        ch = await container.channel_repository.get(link.channel_id)
        if ch is None or ch.company_id != company_id:
            raise HTTPException(status_code=404, detail="Канал ссылки не найден.")
        name = body.scheduled_title.strip()
        if name == "":
            raise HTTPException(status_code=400, detail="scheduled_title не может быть пустым.")
        ch.name = name
        await container.channel_repository.update(ch)
    if body.calendar_member_user_ids is not None:
        await _reconcile_calendar_meeting_channel_members(
            container=container,
            channel_id=link.channel_id,
            company_id=company_id,
            link_creator_user_id=link.created_by_user_id,
            calendar_member_user_ids=body.calendar_member_user_ids,
        )
    updated = await container.call_repository.get_link_for_company(link_token, company_id)
    join_url = await _mint_join_short_url(container, link_token, updated.expires_at)
    return CallLinkRead(
        link_token=updated.link_token,
        channel_id=updated.channel_id,
        call_type="video",
        expires_at=updated.expires_at,
        join_url=join_url,
        title=updated.title,
        scheduled_start_at=updated.scheduled_start_at,
        scheduled_end_at=updated.scheduled_end_at,
        calendar_event_id=updated.calendar_event_id,
    )


@router.delete("/links/{link_token}", status_code=204)
async def delete_call_link(link_token: str, container: ContainerDep) -> None:
    context = get_context()
    company_id = context.active_company.company_id
    user_id = context.user.user_id
    link = await container.call_repository.get_link_for_company(link_token, company_id)
    if link.calendar_event_id is None:
        raise HTTPException(status_code=400, detail="Удаление через этот контракт только для календарных ссылок.")
    role = await container.channel_repository.get_member_role(link.channel_id, user_id)
    if link.created_by_user_id != user_id and role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Нет прав удалить эту ссылку.")
    channel_id = link.channel_id
    deleted = await container.call_repository.delete_link(link_token, company_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Ссылка не найдена.")
    await container.short_link_service.delete_sync_by_link_token(link_token)
    ch = await container.channel_repository.get(channel_id)
    if ch is not None and ch.company_id == company_id and ch.type == CHANNEL_TYPE_CALENDAR_MEETING:
        await container.channel_repository.delete(channel_id)


@router.get("/{call_id}")
async def get_call(call_id: str, container: ContainerDep) -> CallRead:
    """Статус звонка и список участников."""
    context = get_context()
    try:
        call = await container.call_repository.get_call(call_id, context.active_company.company_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    participants = await container.call_repository.list_participants(call_id)
    return _build_call_read(call, participants)


@router.get("/{call_id}/recordings")
async def list_call_recordings(call_id: str, container: ContainerDep) -> list[CallRecordingRead]:
    """Список записей звонка."""
    context = get_context()
    company_id = context.active_company.company_id
    call = await container.call_repository.get_call(call_id, company_id)
    if not await container.channel_repository.is_member(call.channel_id, context.user.user_id, company_id=company_id):
        raise HTTPException(status_code=403, detail="Нет доступа к звонку.")
    rows = await container.call_recording_repository.list_for_call(call_id, company_id)
    return [
        CallRecordingRead(
            recording_id=r.recording_id,
            call_id=r.call_id,
            channel_id=r.channel_id,
            space_id=r.space_id,
            started_by_user_id=r.started_by_user_id,
            status=r.status,
            provider_job_id=r.provider_job_id,
            raw_file_id=r.raw_file_id,
            started_at=r.started_at,
            ended_at=r.ended_at,
            created_at=r.created_at,
            error=r.error,
        )
        for r in rows
    ]


@router.get("/{call_id}/token")
async def get_livekit_token(call_id: str, container: ContainerDep) -> dict:
    """
    Выдаёт LiveKit access token для подключения к SFU-комнате.

    Только для звонков в режиме sfu. Участник должен состоять в канале.
    """
    settings = get_settings()
    context = get_context()
    user_id = context.user.user_id
    company_id = context.active_company.company_id
    try:
        call = await container.call_repository.get_call(call_id, company_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if call.mode != "sfu":
        raise HTTPException(status_code=400, detail=f"Звонок {call_id} не является SFU-звонком.")
    if not call.livekit_room_name:
        raise HTTPException(status_code=400, detail=f"У звонка {call_id} нет LiveKit комнаты.")

    if not await container.channel_repository.is_member(call.channel_id, user_id, company_id=company_id):
        raise HTTPException(status_code=403, detail=f"Нет доступа к каналу звонка {call_id}.")

    token = _livekit_client(settings).generate_token(
        room_name=call.livekit_room_name, identity=user_id
    )
    return {"token": token, "livekit_url": _livekit_public_url(settings)}


# ─── Публичные эндпоинты (без обязательного auth) ────────────────────────────

@router.get("/join/{link_token}")
async def get_link_info(link_token: str, container: ContainerDep) -> CallLinkInfo:
    """
    Публичная информация о ссылке.

    Не требует авторизации — используется страницей /sync/join/{token}
    для отображения канала, создателя и типа звонка.
    """
    settings = get_settings()
    try:
        link = await container.call_repository.get_link(link_token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    channel = await container.channel_repository.get(link.channel_id)
    channel_name = channel.name if channel else None

    creator_name = link.created_by_user_id
    creator_avatar_url: str | None = None
    try:
        user = await container.user_repository.get(link.created_by_user_id)
        if user:
            creator_name = user.name
            creator_avatar_url = user.avatar_url
    except Exception:
        pass

    return CallLinkInfo(
        link_token=link_token,
        channel_name=channel_name,
        creator_display_name=creator_name,
        creator_avatar_url=creator_avatar_url,
        call_type="video",
        expires_at=link.expires_at,
    )


@router.post("/join/{link_token}")
async def join_via_link(
    link_token: str,
    request: Request,
    container: ContainerDep,
    body: Optional[GuestJoinRequest] = None,
) -> JoinResponse:
    """
    Войти в звонок по ссылке.

    - Зарегистрированный пользователь: auth cookie → identity = user_id.
    - Гость: body.guest_name → identity = guest:{uuid}:{name}.

    Первый вход создаёт SFU-звонок; последующие — переиспользуют.
    """
    settings = get_settings()
    try:
        link = await container.call_repository.get_link(link_token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Определяем identity вызывающего.
    # Публичный эндпоинт: анонимный middleware создаёт user_id="anonymous".
    identity: str
    context = get_context()
    is_authenticated = context.user.user_id not in ("anonymous", "", None)

    if is_authenticated:
        identity = context.user.user_id
    else:
        if body is None or not body.guest_name.strip():
            raise HTTPException(status_code=422, detail="Для гостевого входа необходимо указать guest_name.")
        safe_name = body.guest_name.strip().replace(":", "_")
        identity = f"guest:{uuid4().hex[:8]}:{safe_name}"

    # Создаём или переиспользуем звонок (ссылка с заранее привязанным call_id — тот же LiveKit room)
    had_call_on_link = link.call_id is not None
    if link.call_id:
        call = await container.call_repository.get_call(link.call_id, link.company_id)
    else:
        livekit_room_name = f"link-{link_token[:16]}"
        await _livekit_client(settings).create_room(
            livekit_room_name,
            company_id=link.company_id,
            user_id=identity,
        )

        call = SyncCall(
            call_id=uuid4().hex,
            company_id=link.company_id,
            channel_id=link.channel_id,
            mode="sfu",
            call_type="video",
            status="active",
            livekit_room_name=livekit_room_name,
            started_at=datetime.now(UTC),
            created_by_user_id=link.created_by_user_id,
        )
        await container.call_repository.create_call(call)
        await container.call_repository.attach_call_to_link(link_token, call.call_id)

    if not call.livekit_room_name:
        raise ValueError("У звонка нет LiveKit комнаты.")

    logger.info(
        "join_via_link link=%s had_call_on_link=%s call_id=%s livekit_room=%s identity=%s",
        link_token[:12],
        had_call_on_link,
        call.call_id,
        call.livekit_room_name,
        identity[:24] if identity else "",
    )

    token = _livekit_client(settings).generate_token(
        room_name=call.livekit_room_name,
        identity=identity,
    )

    participant_names = await _participant_names_for_call(container, call)

    return JoinResponse(
        call_id=call.call_id,
        call_type="video",
        livekit_token=token,
        livekit_url=_livekit_public_url(settings),
        identity=identity,
        meeting_admin_user_id=call.created_by_user_id,
        mode="sfu",
        participant_names=participant_names,
    )
