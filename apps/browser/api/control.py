"""
Browser Control HTTP API (§17.3): сессии, navigate, observe, action.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from apps.browser.control.ax_snapshot import dom_accessibility_tree_dict_from_page
from apps.browser.control.snapshot_refs import build_interactive_snapshot_with_refs, parse_ref
from apps.browser.control.types import BrowserCapabilityError
from apps.browser.dependencies import ContainerDep
from apps.browser.runtime.types import (
    BrowserAcquireRequest,
    BrowserFetchRequest,
    ContextSignature,
)

router = APIRouter(prefix="/control", tags=["browser-control"])


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
    model_config = ConfigDict(extra="forbid")

    proxy_policy: str = ""
    shared_storage_key: Optional[str] = None
    anti_bot_tier: Literal["white", "gray", "black"] = "white"
    stealth_init_version: str = "v1"
    locale: str = "en-US"
    timezone_id: str = "UTC"
    user_agent: Optional[str] = None
    page_mode: Literal["interactive", "crawl", "lite"] = "interactive"
    permissions_fingerprint: str = "default"
    emulate_locale_timezone_via_cdp: bool = True


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
    model_config = ConfigDict(extra="forbid")

    session_id: Optional[str] = None
    run_id: Optional[str] = None
    task_id: Optional[str] = None
    page_mode: Literal["interactive", "crawl", "lite"] = "interactive"
    shared_storage_key: Optional[str] = None
    proxy_policy: str = ""
    anti_bot_tier: str = "white"
    timeout_ms: int = Field(default=60_000, ge=1000)
    endpoint_key: Optional[str] = None
    session_mode: Literal["warm", "restore"] = "warm"
    restore_state_key: Optional[str] = None
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
    model_config = ConfigDict(extra="forbid")

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
    model_config = ConfigDict(extra="forbid")

    url: str
    wait_policy: str = "domcontentloaded"
    screenshot: bool = False
    snapshot: bool = False
    capture_pdf: bool = False
    navigation_timeout_ms: int = Field(default=60_000, ge=1000)


class ControlObserveBody(BaseModel):
    """
    HTTP-модель входа для `observe`.

    Связи:
    - Управляет тем, какие проекции состояния страницы формируются в ответе.

    Инварианты:
    - `budget` ограничен диапазоном `1..5000`.

    Мотивация:
    - Дать клиенту управляемый профиль наблюдения без отдельных endpoint-ов.

    Переиспользование:
    - Стоит: как универсальная модель observe-запроса.
    """
    model_config = ConfigDict(extra="forbid")

    budget: int = Field(default=80, ge=1, le=5000)
    include_html: bool = False
    include_visibility: bool = True
    include_ax: bool = False
    include_snapshot: bool = False
    include_snapshot_refs: bool = True
    include_listeners: bool = False
    include_dom_diff: bool = False
    emit_generic_role: bool = False


class ControlActionBody(BaseModel):
    """
    HTTP-модель входа для `action`.

    Связи:
    - Передаётся в `control_adapter.run_action`.

    Инварианты:
    - `timeout_ms` валидируется pydantic-ограничением.

    Мотивация:
    - Явно ограничить contract для sandbox-выполнения кода.

    Переиспользование:
    - Стоит: как единая входная модель для action/exec endpoint-ов.
    """
    model_config = ConfigDict(extra="forbid")

    code: str
    timeout_ms: int = Field(default=30_000, ge=1000)


class ControlClickBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str
    timeout_ms: int = Field(default=20_000, ge=1000)


class ControlFillBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str
    text: str
    timeout_ms: int = Field(default=20_000, ge=1000)


class ControlPressBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str


class ControlWaitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selector: Optional[str] = None
    load_state: Optional[Literal["domcontentloaded", "networkidle"]] = None
    timeout_ms: int = Field(default=60_000, ge=1000)


def _features_dict(runtime: Any) -> dict[str, bool]:
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
        emulate_locale_timezone_via_cdp=ctx.emulate_locale_timezone_via_cdp,
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
        raise HTTPException(status_code=501, detail=exc.to_dict()) from exc
    return ControlSessionCreateResponse(
        session_id=sid,
        run_id=run_id,
        task_id=task_id,
        cold_start=res.cold_start,
        endpoint_key=res.endpoint_key,
        context_signature_hash=res.context_signature_hash,
        features=_features_dict(runtime),
    )


@router.post("/sessions/{session_id}/navigate")
async def control_navigate(
    session_id: str,
    body: ControlNavigateBody,
    container: ContainerDep,
) -> dict[str, Any]:
    runtime = container.browser_runtime
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
        raise HTTPException(status_code=501, detail=exc.to_dict()) from exc
    return {
        "final_url": out.final_url,
        "status_code": out.status_code,
        "response_headers": out.response_headers,
        "screenshot_ref": out.screenshot_ref,
        "pdf_ref": out.pdf_ref,
        "snapshot_ref": out.snapshot_ref,
        "anti_bot_signals": out.anti_bot_signals,
    }


@router.post("/sessions/{session_id}/observe")
async def control_observe(
    session_id: str,
    body: ControlObserveBody,
    container: ContainerDep,
) -> dict[str, Any]:
    runtime = container.browser_runtime
    try:
        page = await runtime.lease_manager.get_page_for_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    adapter = runtime.control_adapter
    payload: dict[str, Any] = {"session_id": session_id, "url": page.url}
    vis: dict[str, Any] | None = None
    if body.include_visibility:
        try:
            vis = await adapter.get_visibility_tree(
                page,
                budget=body.budget,
                emit_generic_role=body.emit_generic_role,
            )
        except BrowserCapabilityError as exc:
            raise HTTPException(status_code=501, detail=exc.to_dict()) from exc
        payload["visibility"] = vis
    if body.include_ax:
        try:
            payload["accessibility"] = await adapter.get_accessibility_tree(
                page,
                emit_generic_role=body.emit_generic_role,
            )
        except BrowserCapabilityError as exc:
            raise HTTPException(status_code=501, detail=exc.to_dict()) from exc
    if body.include_snapshot:
        # Snapshot для LLM строим преимущественно на JS-дереве (page.evaluate),
        # без зависимости от Playwright accessibility API.
        ax = await dom_accessibility_tree_dict_from_page(
            page,
            emit_generic_role=body.emit_generic_role,
        )
        snap_text, refs = build_interactive_snapshot_with_refs(ax)
        payload["snapshot"] = {
            "schema": "browser.control.snapshot.v1",
            "mode": "interactive",
            "text": snap_text,
        }
        if body.include_snapshot_refs:
            payload["snapshot"]["refs"] = refs
            runtime.observe_store.update_refs(session_id, refs)
    if body.include_listeners:
        payload["dom_event_listeners"] = await adapter.get_dom_event_listeners(page)
    if body.include_html:
        html = await page.content()
        payload["html"] = html
        fp = hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest()
        html_changed = runtime.observe_store.html_changed(session_id, fp)
        payload["html_fingerprint_sha256"] = fp
        payload["html_changed"] = html_changed
    if body.include_dom_diff:
        if vis is None:
            try:
                vis = await adapter.get_visibility_tree(page, budget=body.budget)
                payload["visibility"] = vis
            except BrowserCapabilityError as exc:
                raise HTTPException(status_code=501, detail=exc.to_dict()) from exc
        diff = runtime.observe_store.diff_visibility(session_id, vis)
        payload["visibility_diff"] = diff
    elif body.include_visibility and vis is not None:
        runtime.observe_store.diff_visibility(session_id, vis)
    return payload


@router.post("/sessions/{session_id}/action")
async def control_action(
    session_id: str,
    body: ControlActionBody,
    container: ContainerDep,
) -> dict[str, Any]:
    runtime = container.browser_runtime
    try:
        page = await runtime.lease_manager.get_page_for_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        return await runtime.control_adapter.run_action(
            page,
            body.code,
            timeout_ms=body.timeout_ms,
        )
    except BrowserCapabilityError as exc:
        raise HTTPException(status_code=501, detail=exc.to_dict()) from exc


def _locator_from_ref(page: Any, refs: dict[str, dict[str, object]], raw_ref: str) -> Any:
    ref = parse_ref(raw_ref)
    if ref not in refs:
        raise HTTPException(status_code=422, detail=f"ref не найден в последнем snapshot: {raw_ref!r}")
    meta = refs[ref]
    role = meta.get("role")
    name = meta.get("name")
    nth = meta.get("nth")
    if not isinstance(role, str) or not role:
        raise HTTPException(status_code=500, detail=f"refs[{ref}].role должен быть непустой строкой")
    if not isinstance(name, str):
        raise HTTPException(status_code=500, detail=f"refs[{ref}].name должен быть строкой")
    if not isinstance(nth, int) or nth < 0:
        raise HTTPException(status_code=500, detail=f"refs[{ref}].nth должен быть int >= 0")
    loc = page.get_by_role(role, name=name, exact=True)
    if nth:
        loc = loc.nth(nth)
    return loc


@router.post("/sessions/{session_id}/click")
async def control_click(
    session_id: str,
    body: ControlClickBody,
    container: ContainerDep,
) -> dict[str, Any]:
    runtime = container.browser_runtime
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
    await loc.click(timeout=body.timeout_ms)
    return {"ok": True}


@router.post("/sessions/{session_id}/fill")
async def control_fill(
    session_id: str,
    body: ControlFillBody,
    container: ContainerDep,
) -> dict[str, Any]:
    runtime = container.browser_runtime
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
    await loc.fill(body.text, timeout=body.timeout_ms)
    return {"ok": True}


@router.post("/sessions/{session_id}/press")
async def control_press(
    session_id: str,
    body: ControlPressBody,
    container: ContainerDep,
) -> dict[str, Any]:
    runtime = container.browser_runtime
    try:
        page = await runtime.lease_manager.get_page_for_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await page.keyboard.press(body.key)
    return {"ok": True}


@router.post("/sessions/{session_id}/wait")
async def control_wait(
    session_id: str,
    body: ControlWaitBody,
    container: ContainerDep,
) -> dict[str, Any]:
    runtime = container.browser_runtime
    try:
        page = await runtime.lease_manager.get_page_for_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if body.load_state is not None:
        await page.wait_for_load_state(body.load_state, timeout=body.timeout_ms)
    if body.selector is not None:
        await page.wait_for_selector(body.selector, timeout=body.timeout_ms)
    if body.load_state is None and body.selector is None:
        raise HTTPException(status_code=422, detail="Нужно задать selector и/или load_state")
    return {"ok": True}


@router.delete("/sessions/{session_id}")
async def delete_control_session(
    session_id: str,
    container: ContainerDep,
) -> dict[str, str]:
    runtime = container.browser_runtime
    await runtime.lease_manager.kill_session(
        session_id,
        warm_idle_sec=runtime.settings.warm_idle_sec,
    )
    runtime.observe_store.forget(session_id)
    return {"status": "closed"}
