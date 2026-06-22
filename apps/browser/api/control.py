""""
HTTP API Browser Control (§17.3): сессии, navigate, observe, action.
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from typing import Annotated, ClassVar, Literal, TypedDict, cast

from fastapi import APIRouter, HTTPException, Query, Response
from playwright.async_api import Error as PlaywrightError
from pydantic import BaseModel, ConfigDict, Field

from apps.browser.contracts.control_types import (
    BrowserCapabilityError,
    ControlHumanTakeoverBody,
    ControlPointerClickBody,
    ControlPointerKeyBody,
    ControlPointerTextBody,
    ControlSessionStatusResponse,
)
from apps.browser.dependencies import ContainerDep
from apps.browser.engine.types import (
    BrowserAcquireRequest,
    BrowserFetchRequest,
    BrowserLocator,
    BrowserPage,
    ContextSignature,
)
from apps.browser.interaction.human_interaction import HumanInteraction, InteractionRng
from apps.browser.interaction.interaction_profiles import (
    InteractionProfile,
    InteractionProfileName,
    get_interaction_profile,
)
from apps.browser.observe.ax_snapshot import dom_accessibility_tree_dict_from_page
from apps.browser.observe.snapshot_refs import (
    RefMap,
    build_interactive_snapshot_with_refs,
    parse_ref,
)
from apps.browser.orchestration.runtime_facade import BrowserRuntimeFacade
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)

router = APIRouter(prefix="/control", tags=["browser-control"])

AGENT_CONTROL_TAKEOVER_WAIT_SEC = 300.0
AGENT_CONTROL_TAKEOVER_POLL_SEC = 0.25


class ControlNavigateResponse(TypedDict):
    final_url: str
    status_code: int | None
    response_headers: dict[str, str]
    screenshot_ref: str | None
    pdf_ref: str | None
    snapshot_ref: str | None
    anti_bot_signals: JsonObject


class ControlSnapshotResponse(TypedDict, total=False):
    schema: str
    mode: str
    text: str
    refs: RefMap


class ControlObserveResponse(TypedDict):
    session_id: str
    url: str
    snapshot: ControlSnapshotResponse


class ControlOkResponse(TypedDict):
    ok: bool


class ControlPointerClickResponse(TypedDict):
    ok: bool
    x: float
    y: float
    viewport_width: float
    viewport_height: float
    url: str


class ControlHumanTakeoverResponse(TypedDict):
    ok: bool
    human_takeover: bool
    owner: str | None


class ControlDeleteResponse(TypedDict):
    status: str


async def wait_for_agent_control(runtime: BrowserRuntimeFacade, session_id: str) -> None:
    deadline = time.monotonic() + AGENT_CONTROL_TAKEOVER_WAIT_SEC
    while True:
        takeover = await runtime.lease_manager.human_takeover_for_session(session_id)
        if takeover is None:
            return
        if time.monotonic() >= deadline:
            raise HTTPException(
                status_code=423,
                detail=(
                    f"browser session {session_id} is under human control by {takeover.owner}; "
                    "release human takeover to resume agent control"
                ),
            )
        await asyncio.sleep(AGENT_CONTROL_TAKEOVER_POLL_SEC)


@asynccontextmanager
async def _agent_control_exclusive(
    runtime: BrowserRuntimeFacade,
    session_id: str,
) -> AsyncGenerator[None]:
    await wait_for_agent_control(runtime, session_id)
    async with runtime.lease_manager.session_navigate_exclusive(session_id):
        await wait_for_agent_control(runtime, session_id)
        yield


def _log_control_event(
    *,
    op: str,
    session_id: str,
    meta: JsonObject | None = None,
    error: JsonObject | None = None,
) -> None:
    """
    Структурный лог шага control API в Loki (сквозной request_id), вместо файлов на диске.
    """
    fields: JsonObject = {"op": op, "session_id": session_id}
    if meta is not None:
        fields["meta"] = meta
    if error is not None:
        fields["error"] = error
        logger.error("browser.control.event_failed", **fields)
        return
    logger.info("browser.control.event", **fields)


class ContextSignatureBody(BaseModel):
    """
    HTTP-модель сигнатуры контекста для create-session.

    Связи:
    - Преобразуется в runtime `ContextSignature`.

    Инварианты:
    - Принимает только явно объявленные поля (`extra="forbid"`).
    - `page_mode` ограничен поддержанными режимами.

    Мотивация:
    - Отделить пользовательский JSON от внутреннего runtime `ContextSignature`.

    Переиспользование:
    - Стоит: как входной DTO для любых API-методов, где нужна сигнатура контекста.
    """
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    proxy_policy: str = ""
    shared_storage_key: str | None = None
    anti_bot_tier: Literal["white", "gray", "black"] = "white"
    stealth_init_version: str = "v1"
    locale: str = "en-US"
    timezone_id: str = "UTC"
    user_agent: str | None = None
    page_mode: Literal["interactive", "crawl", "lite"] = "interactive"
    permissions_fingerprint: str = "default"
    interaction_profile: InteractionProfileName = "human"
    interaction_seed: int | None = None


class ControlSessionCreateBody(BaseModel):
    """
    HTTP-модель входа для `POST /control/sessions`.

    Связи:
    - Маппится в `BrowserAcquireRequest`.

    Инварианты:
    - `timeout_ms` валидируется pydantic-ограничением.
    - `session_mode` ограничен `warm|restore`.

    Мотивация:
    - Собрать все параметры запуска сессии в один валидационный контракт.

    Переиспользование:
    - Стоит: как единая модель create-session для API и тестов.
    """
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    session_id: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    page_mode: Literal["interactive", "crawl", "lite"] = "interactive"
    shared_storage_key: str | None = None
    proxy_policy: str = ""
    anti_bot_tier: str = "white"
    timeout_ms: int = Field(default=60_000, ge=1000)
    endpoint_key: str | None = None
    session_mode: Literal["warm", "restore"] = "warm"
    restore_state_key: str | None = None
    context: ContextSignatureBody = Field(default_factory=ContextSignatureBody)


class ControlSessionCreateResponse(BaseModel):
    """
    HTTP-модель ответа create-session.

    Связи:
    - Формируется из `BrowserAcquireResult` и capability-флагов адаптера.

    Инварианты:
    - Ответ не содержит лишних полей (`extra="forbid"`).

    Мотивация:
    - Зафиксировать стабильный формат ответа независимо от backend-а.

    Переиспользование:
    - Стоит: как каноничный response-model create-session.
    """
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    session_id: str
    run_id: str
    task_id: str
    cold_start: bool
    endpoint_key: str
    context_signature_hash: str
    features: dict[str, bool]


class ControlNavigateBody(BaseModel):
    """
    HTTP-модель входа для `navigate`.

    Связи:
    - Преобразуется в `BrowserFetchRequest`.

    Инварианты:
    - `navigation_timeout_ms` валидируется pydantic-ограничением.

    Мотивация:
    - Явно отделить параметры навигации от runtime DTO.

    Переиспользование:
    - Стоит: для любых endpoint-ов, выполняющих fetch/navigation.
    """
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    url: str
    wait_policy: str = "domcontentloaded"
    screenshot: bool = False
    snapshot: bool = False
    capture_pdf: bool = False
    navigation_timeout_ms: int = Field(default=5_000, ge=1000)
    new_tab: bool = True # костыль, откатить потом.


class ControlObserveBody(BaseModel):
    """
    HTTP-модель входа для `observe`.

    `include_snapshot_refs`: включить объект `snapshot.refs` в теле ответа.
    Маппинг ref -> (role, name, nth) для click/fill всегда сохраняется на сервере
    после observe; без дубля в JSON ответ меньше по токенам, refs в тексте
    snapshot достаточно модели для выбора @eN.
    """
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
    include_snapshot_refs: bool = True


class ControlActionBody(BaseModel):
    """
    HTTP-модель входа для `action`.

    Связи:
    - Передаётся в `control_adapter.run_action`.

    Инварианты:
    - `timeout_ms` валидируется pydantic-ограничением.

    Переиспользование:
    - Стоит: как единая входная модель для action/exec endpoint-ов.
    """
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    code: str
    timeout_ms: int = Field(default=5_000, ge=1000)


class ControlClickBody(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    ref: str
    timeout_ms: int = Field(default=5_000, ge=1000)


class ControlFillBody(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    ref: str
    text: str
    timeout_ms: int = Field(default=5_000, ge=1000)
    typing_delay_ms: int | None = Field(default=None, ge=0)


class ControlPressBody(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    key: str


class ControlWaitBody(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    selector: str | None = None
    load_state: Literal["domcontentloaded", "networkidle"] | None = None
    timeout_ms: int = Field(default=5_000, ge=1000)


def _features_dict(runtime: BrowserRuntimeFacade) -> dict[str, bool]:
    f = runtime.control_adapter.features()
    return {
        "supports_js_injection_dom_tree": f.supports_js_injection_dom_tree,
        "supports_cdp_dom_snapshot": f.supports_cdp_dom_snapshot,
        "supports_cdp_event_listeners": f.supports_cdp_event_listeners,
        "supports_ax_tree": f.supports_ax_tree,
        "supports_selector_map": f.supports_selector_map,
    }


@router.post("/sessions", response_model=ControlSessionCreateResponse)
async def create_control_session(
    body: ControlSessionCreateBody,
    container: ContainerDep,
) -> ControlSessionCreateResponse:
    runtime = container.browser_runtime
    settings = runtime.settings
    sid = body.session_id if body.session_id else f"sess-{uuid.uuid4().hex}"
    run_id = body.run_id if body.run_id else f"run-{sid}"
    task_id = body.task_id if body.task_id else f"task-{sid}"
    endpoint_key = body.endpoint_key if body.endpoint_key else settings.default_endpoint_key
    ctx = body.context
    if ctx.page_mode != body.page_mode:
        raise HTTPException(
            status_code=422,
            detail="context.page_mode должен совпадать с page_mode",
        )
    _ = get_interaction_profile(ctx.interaction_profile)
    sig = ContextSignature(
        proxy_policy=ctx.proxy_policy,
        shared_storage_key=ctx.shared_storage_key,
        anti_bot_tier=ctx.anti_bot_tier,
        stealth_init_version=ctx.stealth_init_version,
        locale=ctx.locale,
        timezone_id=ctx.timezone_id,
        user_agent=ctx.user_agent,
        page_mode=ctx.page_mode,
        permissions_fingerprint=ctx.permissions_fingerprint,
    )
    req = BrowserAcquireRequest(
        run_id=run_id,
        task_id=task_id,
        session_id=sid,
        page_mode=body.page_mode,
        shared_storage_key=body.shared_storage_key,
        proxy_policy=body.proxy_policy,
        anti_bot_tier=body.anti_bot_tier,
        timeout_ms=body.timeout_ms,
        endpoint_key=endpoint_key,
        session_mode=body.session_mode,
        restore_state_key=body.restore_state_key,
        context_signature=sig,
    )
    try:
        res = await runtime.control_adapter.start(req)
    except BrowserCapabilityError as exc:
        _log_control_event(
            op="control.create_session",
            session_id=sid,
            meta={"transport": "http", "path": "/control/sessions"},
            error={"kind": "capability_error", "detail": exc.to_dict()},
        )
        raise HTTPException(status_code=501, detail=exc.to_dict()) from exc
    runtime.observe_store.set_interaction_config(
        sid,
        profile=ctx.interaction_profile,
        seed=ctx.interaction_seed,
    )
    out = ControlSessionCreateResponse(
        session_id=sid,
        run_id=run_id,
        task_id=task_id,
        cold_start=res.cold_start,
        endpoint_key=res.endpoint_key,
        context_signature_hash=res.context_signature_hash,
        features=_features_dict(runtime),
    )
    _log_control_event(
        op="control.create_session",
        session_id=sid,
        meta={"transport": "http", "path": "/control/sessions"},
    )
    return out


@router.post("/sessions/{session_id}/navigate")
async def control_navigate(
    session_id: str,
    body: ControlNavigateBody,
    container: ContainerDep,
) -> ControlNavigateResponse:
    runtime = container.browser_runtime
    async with _agent_control_exclusive(runtime, session_id):
        if body.new_tab:
            try:
                page = await runtime.lease_manager.swap_active_page_for_session(session_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except RuntimeError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            runtime.observe_store.clear_refs(session_id)
        else:
            try:
                page = await runtime.lease_manager.get_page_for_session(session_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except RuntimeError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        req = BrowserFetchRequest(
            url=body.url,
            wait_policy=body.wait_policy,
            screenshot=body.screenshot,
            snapshot=body.snapshot,
            capture_pdf=body.capture_pdf,
            navigation_timeout_ms=body.navigation_timeout_ms,
        )
        try:
            out = await runtime.control_adapter.navigate(page, req)
        except BrowserCapabilityError as exc:
            _log_control_event(
                op="control.navigate",
                session_id=session_id,
                meta={"transport": "http", "path": f"/control/sessions/{session_id}/navigate"},
                error={"kind": "capability_error", "detail": exc.to_dict()},
            )
            raise HTTPException(status_code=501, detail=exc.to_dict()) from exc

        # После навигации даём небольшой "поведенческий" шум в профилях human/fast,
        # чтобы приближать сессию к пользовательской (crawl4ai-like simulate_user).
        try:
            inter, profile, rnd = _interaction_for_session(runtime, session_id)
            await inter.post_navigate_signals(page, profile=profile, rnd=rnd)
        except HTTPException:
            raise
        except Exception:
            # Поведенческий слой не должен ломать навигацию: это best-effort сигнал,
            # а не обязательная часть контракта navigate.
            pass
        payload: ControlNavigateResponse = {
            "final_url": out.final_url,
            "status_code": out.status_code,
            "response_headers": out.response_headers,
            "screenshot_ref": out.screenshot_ref,
            "pdf_ref": out.pdf_ref,
            "snapshot_ref": out.snapshot_ref,
            "anti_bot_signals": out.anti_bot_signals,
        }
        _log_control_event(
            op="control.navigate",
            session_id=session_id,
            meta={
                "transport": "http",
                "path": f"/control/sessions/{session_id}/navigate",
                "final_url": out.final_url,
                "status_code": out.status_code,
            },
        )
        return payload


@router.post("/sessions/{session_id}/observe")
async def control_observe(
    session_id: str,
    body: ControlObserveBody,
    container: ContainerDep,
) -> ControlObserveResponse:
    runtime = container.browser_runtime
    async with _agent_control_exclusive(runtime, session_id):
        try:
            page = await runtime.lease_manager.get_page_for_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        payload: ControlObserveResponse = {
            "session_id": session_id,
            "url": page.url,
            "snapshot": {
                "schema": "browser.control.snapshot.v1",
                "mode": "interactive",
                "text": "",
            },
        }

        # Observe должен работать на "готовой" странице: domcontentloaded достаточно.
        # `networkidle` на Lightpanda и на сайтах с трекерами может не наступать (или падать),
        # а observe не должен зависеть от аналитики/рекламы.
        await page.wait_for_load_state("domcontentloaded", timeout=10_000)

        # Каноничный LLM-friendly snapshot: строим строго через JS в странице (page.evaluate),
        # без зависимости от Playwright accessibility API и без тяжёлых «сырьевых» деревьев.
        ax = await dom_accessibility_tree_dict_from_page(page)
        snap_text, refs = build_interactive_snapshot_with_refs(ax)
        snapshot: ControlSnapshotResponse = {
            "schema": "browser.control.snapshot.v1",
            "mode": "interactive",
            "text": snap_text,
        }
        payload["snapshot"] = snapshot
        runtime.observe_store.update_refs(session_id, refs)
        # if body.include_snapshot_refs:  # отключено
        snapshot["refs"] = refs

        _log_control_event(
            op="control.observe",
            session_id=session_id,
            meta={
                "transport": "http",
                "path": f"/control/sessions/{session_id}/observe",
                "url": page.url,
                "refs_count": len(refs),
                "include_snapshot_refs": body.include_snapshot_refs,
            },
        )
        return payload


@router.post("/sessions/{session_id}/action")
async def control_action(
    session_id: str,
    body: ControlActionBody,
    container: ContainerDep,
) -> JsonObject:
    runtime = container.browser_runtime
    async with _agent_control_exclusive(runtime, session_id):
        try:
            page = await runtime.lease_manager.get_page_for_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        try:
            out = await runtime.control_adapter.run_action(
                page,
                body.code,
                timeout_ms=body.timeout_ms,
            )
            _log_control_event(
                op="control.action",
                session_id=session_id,
                meta={"transport": "http", "path": f"/control/sessions/{session_id}/action"},
            )
            return out
        except BrowserCapabilityError as exc:
            _log_control_event(
                op="control.action",
                session_id=session_id,
                meta={"transport": "http", "path": f"/control/sessions/{session_id}/action"},
                error={"kind": "capability_error", "detail": exc.to_dict()},
            )
            raise HTTPException(status_code=501, detail=exc.to_dict()) from exc


def _locator_from_ref(page: BrowserPage, refs: RefMap, raw_ref: str) -> BrowserLocator:
    ref = parse_ref(raw_ref)
    if ref not in refs:
        raise HTTPException(status_code=422, detail=f"ref не найден в последнем snapshot: {raw_ref!r}")
    meta = refs[ref]
    role = meta.get("role")
    name = meta.get("name")
    nth = meta.get("nth")
    if not role:
        raise HTTPException(status_code=500, detail=f"refs[{ref}].role должен быть непустой строкой")
    if nth < 0:
        raise HTTPException(status_code=500, detail=f"refs[{ref}].nth должен быть int >= 0")
    loc = page.get_by_role(role, name=name, exact=True)
    if nth:
        loc = loc.nth(nth)
    return loc


def _interaction_for_session(
    runtime: BrowserRuntimeFacade,
    session_id: str,
) -> tuple[HumanInteraction, InteractionProfile, InteractionRng]:
    try:
        profile_name = runtime.observe_store.get_interaction_profile(session_id)
        profile = get_interaction_profile(profile_name)
        seed, step = runtime.observe_store.next_interaction_nonce(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # Детерминированный RNG: одна сессия -> одна последовательность, отличная между действиями.
    mixed = (seed + (step + 1) * 1_000_003) & ((1 << 64) - 1)
    rnd = InteractionRng(random.Random(mixed))
    return HumanInteraction(), profile, rnd


@router.post("/sessions/{session_id}/click")
async def control_click(
    session_id: str,
    body: ControlClickBody,
    container: ContainerDep,
) -> ControlOkResponse:
    runtime = container.browser_runtime
    async with _agent_control_exclusive(runtime, session_id):
        try:
            page = await runtime.lease_manager.get_page_for_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        try:
            refs = runtime.observe_store.get_refs(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        loc = _locator_from_ref(page, refs, body.ref)
        await loc.wait_for(state="visible", timeout=body.timeout_ms)
        inter, profile, rnd = _interaction_for_session(runtime, session_id)
        await inter.click(page, loc, profile=profile, rnd=rnd, timeout_ms=body.timeout_ms)
        out: ControlOkResponse = {"ok": True}
        _log_control_event(
            op="control.click",
            session_id=session_id,
            meta={"transport": "http", "path": f"/control/sessions/{session_id}/click"},
        )
        return out


async def _viewport_size(
    page: BrowserPage,
    *,
    fallback_width: float,
    fallback_height: float,
) -> tuple[float, float]:
    size = page.viewport_size
    if size is not None:
        width = size["width"]
        height = size["height"]
        if width > 0 and height > 0:
            return float(width), float(height)
    js_size = cast(
        object,
        await page.evaluate(
            "() => ({ "
            + "width: window.innerWidth || document.documentElement.clientWidth, "
            + "height: window.innerHeight || document.documentElement.clientHeight "
            + "})"
        ),
    )
    if isinstance(js_size, dict):
        js_size_map = cast(Mapping[object, object], js_size)
        width = js_size_map.get("width")
        height = js_size_map.get("height")
        if isinstance(width, (int, float)) and isinstance(height, (int, float)) and width > 0 and height > 0:
            return float(width), float(height)
    return float(fallback_width), float(fallback_height)


@router.post("/sessions/{session_id}/pointer/click")
async def control_pointer_click(
    session_id: str,
    body: ControlPointerClickBody,
    container: ContainerDep,
) -> ControlPointerClickResponse:
    runtime = container.browser_runtime
    try:
        page = await runtime.lease_manager.get_page_for_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        viewport_width, viewport_height = await _viewport_size(
            page,
            fallback_width=body.image_width,
            fallback_height=body.image_height,
        )
        x = max(0.0, min(viewport_width - 1.0, body.x / body.image_width * viewport_width))
        y = max(0.0, min(viewport_height - 1.0, body.y / body.image_height * viewport_height))
        await page.mouse.click(
            x,
            y,
            button=body.button,
            click_count=body.click_count,
        )
        page_url = page.url
    except PlaywrightError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"browser page is not available for pointer click: {exc}",
        ) from exc
    out: ControlPointerClickResponse = {
        "ok": True,
        "x": x,
        "y": y,
        "viewport_width": viewport_width,
        "viewport_height": viewport_height,
        "url": page_url,
    }
    _log_control_event(
        op="control.pointer_click",
        session_id=session_id,
        meta={"transport": "http", "path": f"/control/sessions/{session_id}/pointer/click"},
    )
    return out


@router.post("/sessions/{session_id}/human-takeover")
async def control_human_takeover(
    session_id: str,
    body: ControlHumanTakeoverBody,
    container: ContainerDep,
) -> ControlHumanTakeoverResponse:
    runtime = container.browser_runtime
    try:
        page = await runtime.lease_manager.get_page_for_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if page.is_closed():
        raise HTTPException(status_code=410, detail="browser page is closed")
    record = await runtime.lease_manager.begin_human_takeover(session_id, owner=body.owner)
    out: ControlHumanTakeoverResponse = {
        "ok": True,
        "human_takeover": True,
        "owner": record.owner,
    }
    _log_control_event(
        op="control.human_takeover.begin",
        session_id=session_id,
        meta={"transport": "http", "path": f"/control/sessions/{session_id}/human-takeover"},
    )
    return out


@router.post("/sessions/{session_id}/human-takeover/release")
async def control_human_takeover_release(
    session_id: str,
    container: ContainerDep,
) -> ControlHumanTakeoverResponse:
    runtime = container.browser_runtime
    record = await runtime.lease_manager.end_human_takeover(session_id)
    out: ControlHumanTakeoverResponse = {
        "ok": True,
        "human_takeover": False,
        "owner": record.owner if record is not None else None,
    }
    _log_control_event(
        op="control.human_takeover.release",
        session_id=session_id,
        meta={"transport": "http", "path": f"/control/sessions/{session_id}/human-takeover/release"},
    )
    return out


@router.post("/sessions/{session_id}/pointer/key")
async def control_pointer_key(
    session_id: str,
    body: ControlPointerKeyBody,
    container: ContainerDep,
) -> ControlOkResponse:
    runtime = container.browser_runtime
    try:
        page = await runtime.lease_manager.get_page_for_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        await page.keyboard.press(body.key)
    except PlaywrightError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"browser page is not available for keyboard input: {exc}",
        ) from exc
    out: ControlOkResponse = {"ok": True}
    _log_control_event(
        op="control.pointer_key",
        session_id=session_id,
        meta={"transport": "http", "path": f"/control/sessions/{session_id}/pointer/key"},
    )
    return out


@router.post("/sessions/{session_id}/pointer/text")
async def control_pointer_text(
    session_id: str,
    body: ControlPointerTextBody,
    container: ContainerDep,
) -> ControlOkResponse:
    runtime = container.browser_runtime
    try:
        page = await runtime.lease_manager.get_page_for_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        await page.keyboard.type(body.text)
    except PlaywrightError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"browser page is not available for text input: {exc}",
        ) from exc
    out: ControlOkResponse = {"ok": True}
    _log_control_event(
        op="control.pointer_text",
        session_id=session_id,
        meta={"transport": "http", "path": f"/control/sessions/{session_id}/pointer/text"},
    )
    return out


@router.post("/sessions/{session_id}/fill")
async def control_fill(
    session_id: str,
    body: ControlFillBody,
    container: ContainerDep,
) -> ControlOkResponse:
    runtime = container.browser_runtime
    async with _agent_control_exclusive(runtime, session_id):
        try:
            page = await runtime.lease_manager.get_page_for_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        try:
            refs = runtime.observe_store.get_refs(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        loc = _locator_from_ref(page, refs, body.ref)
        await loc.wait_for(state="visible", timeout=body.timeout_ms)
        inter, profile, rnd = _interaction_for_session(runtime, session_id)
        await inter.type_text(
            page,
            loc,
            body.text,
            profile=profile,
            rnd=rnd,
            timeout_ms=body.timeout_ms,
            typing_delay_ms=body.typing_delay_ms,
        )
        out: ControlOkResponse = {"ok": True}
        _log_control_event(
            op="control.fill",
            session_id=session_id,
            meta={"transport": "http", "path": f"/control/sessions/{session_id}/fill"},
        )
        return out


@router.post("/sessions/{session_id}/press")
async def control_press(
    session_id: str,
    body: ControlPressBody,
    container: ContainerDep,
) -> ControlOkResponse:
    runtime = container.browser_runtime
    async with _agent_control_exclusive(runtime, session_id):
        try:
            page = await runtime.lease_manager.get_page_for_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        inter, profile, rnd = _interaction_for_session(runtime, session_id)
        await inter.press(page, body.key, profile=profile, rnd=rnd)
        out: ControlOkResponse = {"ok": True}
        _log_control_event(
            op="control.press",
            session_id=session_id,
            meta={"transport": "http", "path": f"/control/sessions/{session_id}/press"},
        )
        return out


@router.post("/sessions/{session_id}/wait")
async def control_wait(
    session_id: str,
    body: ControlWaitBody,
    container: ContainerDep,
) -> ControlOkResponse:
    runtime = container.browser_runtime
    async with _agent_control_exclusive(runtime, session_id):
        try:
            page = await runtime.lease_manager.get_page_for_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if body.load_state is not None:
            await page.wait_for_load_state(body.load_state, timeout=body.timeout_ms)
        if body.selector is not None:
            _ = await page.wait_for_selector(body.selector, timeout=body.timeout_ms)
        if body.load_state is None and body.selector is None:
            raise HTTPException(status_code=422, detail="Нужно задать selector и/или load_state")
        out: ControlOkResponse = {"ok": True}
        _log_control_event(
            op="control.wait",
            session_id=session_id,
            meta={"transport": "http", "path": f"/control/sessions/{session_id}/wait"},
        )
        return out


@router.get("/sessions/{session_id}/status", response_model=ControlSessionStatusResponse)
async def control_session_status(
    session_id: str,
    container: ContainerDep,
) -> ControlSessionStatusResponse:
    runtime = container.browser_runtime
    try:
        page = await runtime.lease_manager.get_page_for_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    closed = bool(page.is_closed())
    title = ""
    if not closed:
        try:
            title = await page.title()
        except Exception:
            title = ""
    takeover = await runtime.lease_manager.human_takeover_for_session(session_id)
    return ControlSessionStatusResponse(
        session_id=session_id,
        url=page.url,
        title=title,
        closed=closed,
        human_takeover=takeover is not None,
        human_takeover_owner=takeover.owner if takeover is not None else None,
    )


@router.get("/sessions/{session_id}/screenshot")
async def control_session_screenshot(
    session_id: str,
    container: ContainerDep,
    image_format: Annotated[Literal["jpeg", "png"], Query(alias="format")] = "jpeg",
    quality: Annotated[int, Query(ge=1, le=100)] = 70,
    full_page: Annotated[bool, Query()] = False,
) -> Response:
    runtime = container.browser_runtime
    try:
        page = await runtime.lease_manager.get_page_for_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if page.is_closed():
        raise HTTPException(status_code=410, detail="browser page is closed")

    try:
        if image_format == "jpeg":
            body = await page.screenshot(
                type=image_format,
                full_page=full_page,
                timeout=5_000,
                animations="disabled",
                quality=quality,
            )
        else:
            body = await page.screenshot(
                type=image_format,
                full_page=full_page,
                timeout=5_000,
                animations="disabled",
            )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"screenshot failed: {exc}") from exc
    return Response(
        content=body,
        media_type=f"image/{image_format}",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.delete("/sessions/{session_id}")
async def delete_control_session(
    session_id: str,
    container: ContainerDep,
) -> ControlDeleteResponse:
    runtime = container.browser_runtime
    await runtime.lease_manager.kill_session(
        session_id,
        warm_idle_sec=runtime.settings.warm_idle_sec,
    )
    runtime.observe_store.forget(session_id)
    out: ControlDeleteResponse = {"status": "closed"}
    _log_control_event(
        op="control.close_session",
        session_id=session_id,
        meta={"transport": "http", "path": f"/control/sessions/{session_id}"},
    )
    return out


class ControlSaveStateBody(BaseModel):
    """
    Вход для сохранения состояния сессии (cookies/storage_state) в Redis.
    """
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    shared_storage_key: str


class ControlSaveStateResponse(TypedDict):
    state_key: str


@router.post("/sessions/{session_id}/state")
async def save_control_session_state(
    session_id: str,
    body: ControlSaveStateBody,
    container: ContainerDep,
) -> ControlSaveStateResponse:
    """
    Сохранить состояние активной сессии в Redis и вернуть `state_key`.

    Полученный `state_key` передаётся в create-session как `restore_state_key`,
    чтобы поднять новый контекст с теми же cookies/storage (warm/restore).
    """
    runtime = container.browser_runtime
    try:
        page = await runtime.lease_manager.get_page_for_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    state_key = await runtime.interactor.save_state(page.context, body.shared_storage_key)
    _log_control_event(
        op="control.save_state",
        session_id=session_id,
        meta={"transport": "http", "path": f"/control/sessions/{session_id}/state"},
    )
    return {"state_key": state_key}
