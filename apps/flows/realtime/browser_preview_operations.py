"""Интерактивный browser preview: статус/ввод/перехват управления сессией Browser Runtime.

Доступ даёт подписанный preview-токен из chip'а в чате, а не сессия пользователя
(viewer работает в iframe и может открываться анонимно). Байты (screenshot, HTML viewer)
остаются протокольными REST-хендлерами в `apps/flows/src/api/v1/browser_preview.py`.
"""

from __future__ import annotations

from urllib.parse import quote

from pydantic import BaseModel, Field

from apps.flows.di import Di
from apps.flows.src.services.browser_preview import (
    BrowserPreviewActiveSessionResponse,
    build_browser_preview_urls,
    get_active_browser_session_for_task,
    verify_browser_preview_token,
    verify_browser_preview_token_for_task,
)
from core.clients.browser.control_types import (
    ControlHumanTakeoverBody,
    ControlHumanTakeoverResponse,
    ControlOkResponse,
    ControlPointerClickBody,
    ControlPointerClickResponse,
    ControlPointerKeyBody,
    ControlPointerTextBody,
    ControlSessionStatusResponse,
)
from core.clients.service_client import ServiceClientError
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.types import JsonValue
from core.websocket import (
    raise_conflict,
    raise_forbidden,
    raise_invalid,
    raise_not_found,
    raise_unavailable,
)


class BrowserPreviewSessionPayload(StrictBaseModel):
    session_id: str = Field(min_length=1)
    token: str = Field(min_length=1)


class BrowserPreviewTaskPayload(StrictBaseModel):
    task_id: str = Field(min_length=1)
    token: str = Field(min_length=1)


class BrowserPreviewClickPayload(ControlPointerClickBody):
    session_id: str = Field(min_length=1)
    token: str = Field(min_length=1)


class BrowserPreviewKeyPayload(ControlPointerKeyBody):
    session_id: str = Field(min_length=1)
    token: str = Field(min_length=1)


class BrowserPreviewTextPayload(ControlPointerTextBody):
    session_id: str = Field(min_length=1)
    token: str = Field(min_length=1)


class BrowserPreviewTakeoverPayload(ControlHumanTakeoverBody):
    session_id: str = Field(min_length=1)
    token: str = Field(min_length=1)


def _verify_session_token(payload: BrowserPreviewSessionPayload) -> None:
    try:
        _ = verify_browser_preview_token(token=payload.token, session_id=payload.session_id)
    except ValueError as exc:
        raise_forbidden(exc)


def _control_path(session_id: str, suffix: str) -> str:
    return f"/browser/api/v1/control/sessions/{quote(session_id, safe='')}/{suffix}"


def _detail_text(exc: ServiceClientError) -> str:
    detail = exc.http_detail()
    return detail if isinstance(detail, str) and detail else str(exc)


def _raise_from_browser(exc: ServiceClientError) -> None:
    """Статус Browser Runtime сохраняется: 404 → not_found (viewer уходит в follow-режим)."""
    status_code = exc.status_code
    if status_code == 404:
        raise_not_found(exc, _detail_text(exc))
    if status_code in (409, 410):
        raise_conflict(exc, _detail_text(exc))
    if status_code is not None and 400 <= status_code < 500:
        raise_invalid(ValueError(_detail_text(exc)))
    raise_unavailable(exc)


async def _browser_get(di: Di, session_id: str, suffix: str, *, timeout: float) -> JsonValue:
    try:
        return await di.service_client.get("browser", _control_path(session_id, suffix), timeout=timeout)
    except ServiceClientError as exc:
        _raise_from_browser(exc)
        raise


async def _browser_post(
    di: Di,
    session_id: str,
    suffix: str,
    *,
    body: BaseModel | None,
    timeout: float,
) -> JsonValue:
    json_body = body.model_dump(mode="json") if body is not None else {}
    try:
        return await di.service_client.post(
            "browser", _control_path(session_id, suffix), timeout=timeout, json=json_body
        )
    except ServiceClientError as exc:
        _raise_from_browser(exc)
        raise


async def op_flows_browser_preview_status(
    payload: BrowserPreviewSessionPayload,
    *,
    user: User,
    di: Di,
) -> ControlSessionStatusResponse:
    _ = user
    _verify_session_token(payload)
    response_payload = await _browser_get(di, payload.session_id, "status", timeout=5.0)
    return ControlSessionStatusResponse.model_validate(response_payload)


async def op_flows_browser_preview_active_session(
    payload: BrowserPreviewTaskPayload,
    *,
    user: User,
    di: Di,
) -> BrowserPreviewActiveSessionResponse:
    """Текущая browser-сессия задачи; `session_id=None` — сейчас открытой сессии нет."""
    _ = user, di
    try:
        _ = verify_browser_preview_token_for_task(token=payload.token, task_id=payload.task_id)
    except ValueError as exc:
        raise_forbidden(exc)
    active_session_id = await get_active_browser_session_for_task(payload.task_id)
    if active_session_id is None:
        return BrowserPreviewActiveSessionResponse(session_id=None)
    urls = build_browser_preview_urls(session_id=active_session_id, task_id=payload.task_id)
    return BrowserPreviewActiveSessionResponse(
        session_id=active_session_id,
        viewer_url=urls["viewer_url"],
        screenshot_url=urls["screenshot_url"],
        status_url=urls["status_url"],
    )


async def op_flows_browser_preview_click(
    payload: BrowserPreviewClickPayload,
    *,
    user: User,
    di: Di,
) -> ControlPointerClickResponse:
    _ = user
    _verify_session_token(BrowserPreviewSessionPayload(session_id=payload.session_id, token=payload.token))
    body = ControlPointerClickBody(
        x=payload.x,
        y=payload.y,
        image_width=payload.image_width,
        image_height=payload.image_height,
        button=payload.button,
        click_count=payload.click_count,
    )
    response_payload = await _browser_post(
        di, payload.session_id, "pointer/click", body=body, timeout=10.0
    )
    return ControlPointerClickResponse.model_validate(response_payload)


async def op_flows_browser_preview_key(
    payload: BrowserPreviewKeyPayload,
    *,
    user: User,
    di: Di,
) -> ControlOkResponse:
    _ = user
    _verify_session_token(BrowserPreviewSessionPayload(session_id=payload.session_id, token=payload.token))
    response_payload = await _browser_post(
        di,
        payload.session_id,
        "pointer/key",
        body=ControlPointerKeyBody(key=payload.key),
        timeout=5.0,
    )
    return ControlOkResponse.model_validate(response_payload)


async def op_flows_browser_preview_text(
    payload: BrowserPreviewTextPayload,
    *,
    user: User,
    di: Di,
) -> ControlOkResponse:
    _ = user
    _verify_session_token(BrowserPreviewSessionPayload(session_id=payload.session_id, token=payload.token))
    response_payload = await _browser_post(
        di,
        payload.session_id,
        "pointer/text",
        body=ControlPointerTextBody(text=payload.text),
        timeout=5.0,
    )
    return ControlOkResponse.model_validate(response_payload)


async def op_flows_browser_preview_takeover(
    payload: BrowserPreviewTakeoverPayload,
    *,
    user: User,
    di: Di,
) -> ControlHumanTakeoverResponse:
    _ = user
    _verify_session_token(BrowserPreviewSessionPayload(session_id=payload.session_id, token=payload.token))
    response_payload = await _browser_post(
        di,
        payload.session_id,
        "human-takeover",
        body=ControlHumanTakeoverBody(owner=payload.owner),
        timeout=5.0,
    )
    return ControlHumanTakeoverResponse.model_validate(response_payload)


async def op_flows_browser_preview_takeover_release(
    payload: BrowserPreviewSessionPayload,
    *,
    user: User,
    di: Di,
) -> ControlHumanTakeoverResponse:
    _ = user
    _verify_session_token(payload)
    response_payload = await _browser_post(
        di, payload.session_id, "human-takeover/release", body=None, timeout=5.0
    )
    return ControlHumanTakeoverResponse.model_validate(response_payload)

