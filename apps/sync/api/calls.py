"""REST API для WebRTC звонков."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from apps.sync.container import get_sync_container
from apps.sync.db.models import SyncCall, SyncCallLink
from apps.sync.models.calls import (
    CallLinkCreate,
    CallLinkInfo,
    CallLinkRead,
    CallParticipantRead,
    CallRead,
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


# ─── Авторизованные эндпоинты ────────────────────────────────────────────────

@router.get("/turn-credentials")
async def get_turn_credentials() -> TurnCredentials:
    """Временные TURN credentials для WebRTC ICE (coturn HMAC-SHA1)."""
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
async def create_call_link(body: CallLinkCreate, request: Request) -> CallLinkRead:
    """
    Создаёт постоянную ссылку на звонок.

    По ней может войти любой — зарегистрированный пользователь или гость.
    Звонок создаётся в SFU-режиме при первом входе.
    """
    context = get_context()
    settings = get_settings()
    container = get_sync_container()

    company_id = context.active_company.company_id
    if not await container.channel_repository.is_member(
        body.channel_id, context.user.user_id, company_id=company_id
    ):
        raise HTTPException(status_code=403, detail="Нет доступа к каналу.")

    attached_call_id: Optional[str] = None
    if body.call_id:
        try:
            existing = await container.call_repository.get_call(body.call_id, company_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if existing.channel_id != body.channel_id:
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

    link_token = uuid4().hex
    expires_at = datetime.now(UTC) + timedelta(hours=body.ttl_hours)

    link = SyncCallLink(
        link_token=link_token,
        channel_id=body.channel_id,
        company_id=company_id,
        call_id=attached_call_id,
        call_type="video",
        created_by_user_id=context.user.user_id,
        expires_at=expires_at,
    )
    await container.call_repository.create_link(link)

    base_url = str(request.base_url).rstrip("/")
    join_url = f"{base_url}/sync/join/{link_token}"

    return CallLinkRead(
        link_token=link_token,
        channel_id=body.channel_id,
        call_type="video",
        expires_at=expires_at,
        join_url=join_url,
    )


@router.get("/{call_id}")
async def get_call(call_id: str) -> CallRead:
    """Статус звонка и список участников."""
    context = get_context()
    container = get_sync_container()
    try:
        call = await container.call_repository.get_call(call_id, context.active_company.company_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    participants = await container.call_repository.list_participants(call_id)
    return _build_call_read(call, participants)


@router.get("/{call_id}/recordings")
async def list_call_recordings(call_id: str) -> list[CallRecordingRead]:
    """Список записей звонка."""
    context = get_context()
    container = get_sync_container()
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
async def get_livekit_token(call_id: str) -> dict:
    """
    Выдаёт LiveKit access token для подключения к SFU-комнате.

    Только для звонков в режиме sfu. Участник должен состоять в канале.
    """
    settings = get_settings()
    context = get_context()
    user_id = context.user.user_id
    company_id = context.active_company.company_id

    container = get_sync_container()
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
async def get_link_info(link_token: str) -> CallLinkInfo:
    """
    Публичная информация о ссылке.

    Не требует авторизации — используется страницей /sync/join/{token}
    для отображения канала, создателя и типа звонка.
    """
    settings = get_settings()
    container = get_sync_container()
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
    body: Optional[GuestJoinRequest] = None,
) -> JoinResponse:
    """
    Войти в звонок по ссылке.

    - Зарегистрированный пользователь: auth cookie → identity = user_id.
    - Гость: body.guest_name → identity = guest:{uuid}:{name}.

    Первый вход создаёт SFU-звонок; последующие — переиспользуют.
    """
    settings = get_settings()
    container = get_sync_container()
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
        await _livekit_client(settings).create_room(livekit_room_name)

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
        livekit_token=token,
        livekit_url=_livekit_public_url(settings),
        identity=identity,
        mode="sfu",
        participant_names=participant_names,
    )
