"""
Browser Control HTTP API (§17.3): сессии, navigate, observe, action.
"""

from __future__ import annotations

import json
import random
import re
import uuid
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from apps.browser.contracts.control_types import BrowserCapabilityError
from apps.browser.dependencies import ContainerDep
from apps.browser.engine.types import (
    BrowserAcquireRequest,
    BrowserFetchRequest,
    ContextSignature,
)
from apps.browser.interaction.human_interaction import HumanInteraction, InteractionRng
from apps.browser.interaction.interaction_profiles import (
    InteractionProfileName,
    get_interaction_profile,
)
from apps.browser.observe.ax_snapshot import dom_accessibility_tree_dict_from_page
from apps.browser.observe.snapshot_refs import build_interactive_snapshot_with_refs, parse_ref

router = APIRouter(prefix="/control", tags=["browser-control"])


def _format_console_events_text(events: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for e in events:
        kind = str(e.get("kind", "") or "")
        if kind == "console":
            t = str(e.get("type", "") or "")
            text = str(e.get("text", "") or "")
            loc = e.get("location")
            loc_s = ""
            if isinstance(loc, dict):
                url = loc.get("url")
                line = loc.get("line")
                col = loc.get("column")
                if isinstance(url, str) and url:
                    loc_s = url
                    if isinstance(line, int):
                        loc_s += f":{line}"
                        if isinstance(col, int):
                            loc_s += f":{col}"
            if loc_s:
                lines.append(f"[console.{t}] {text} ({loc_s})")
            else:
                lines.append(f"[console.{t}] {text}")
            continue
        if kind == "pageerror":
            msg = str(e.get("message", "") or "")
            stack = str(e.get("stack", "") or "")
            lines.append(f"[pageerror] {msg}")
            if stack:
                lines.append(stack)
            continue
        if kind == "requestfailed":
            url = str(e.get("url", "") or "")
            method = str(e.get("method", "") or "")
            failure = str(e.get("failure", "") or "")
            if method and url:
                lines.append(f"[requestfailed] {method} {url} ({failure})" if failure else f"[requestfailed] {method} {url}")
            elif url:
                lines.append(f"[requestfailed] {url} ({failure})" if failure else f"[requestfailed] {url}")
            else:
                lines.append(json.dumps(e, ensure_ascii=False))
            continue
        if kind == "http_error":
            url = str(e.get("url", "") or "")
            status = e.get("status")
            if isinstance(status, int) and url:
                lines.append(f"[http.{status}] {url}")
            else:
                lines.append(json.dumps(e, ensure_ascii=False))
            continue
        lines.append(json.dumps(e, ensure_ascii=False))
    return "\n".join(lines).strip() + ("\n" if len(lines) else "")


def _write_console_sidecars(*, runtime: Any, session_id: str, event_path: str) -> None:
    events = runtime.lease_manager.drain_console_events(session_id)
    json_path = runtime.session_artifacts.write_sidecar_text_for_event(
        event_json_path=event_path,
        ext=".console.json",
        content=json.dumps(events, ensure_ascii=False, indent=2),
    )
    txt_path = runtime.session_artifacts.write_sidecar_text_for_event(
        event_json_path=event_path,
        ext=".console.txt",
        content=_format_console_events_text(events),
    )
    page_events_log_ref = runtime.session_artifacts.append_jsonl_for_session(
        session_id=session_id,
        filename="page_events.jsonl",
        record={"kind": "checkpoint", "op": "drain_console_events", "count": len(events)},
    )
    runtime.session_artifacts.patch_event_meta(
        event_json_path=event_path,
        meta_patch={
            "console_events": {
                "count": len(events),
                "json_ref": json_path,
                "text_ref": txt_path,
            },
            "page_events_log_ref": page_events_log_ref,
        },
    )


def _extract_page_error_from_html(html: str) -> dict[str, str] | None:
    """
    Лучшее усилие: вытащить "ошибку страницы" из HTML.

    Это не CDP exception, а диагностический маркер, когда сайт отдаёт error-screen
    (например Habr: tm-error-message / "Internal error").
    """
    if not html:
        return None
    if "tm-error-message__title" not in html:
        return None
    title_m = re.search(r'tm-error-message__title"\s*>\s*([^<]+)\s*<', html)
    body_m = re.search(r'tm-error-message__body"\s*>\s*<p[^>]*>\s*([^<]+)\s*<', html)
    title = title_m.group(1).strip() if title_m else ""
    body = body_m.group(1).strip() if body_m else ""
    if not title and not body:
        return None
    out: dict[str, str] = {}
    if title:
        out["title"] = title
    if body:
        out["message"] = body
    return out if out else None


def _write_session_event(
    *,
    runtime: Any,
    session_id: str,
    op: str,
    request: Any,
    response: Any,
    error: Any,
    meta: dict[str, Any],
) -> str:
    return runtime.session_artifacts.write_event(
        session_id=session_id,
        op=op,
        request=request,
        response=response,
        error=error,
        meta=meta,
    )


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
    interaction_profile: InteractionProfileName = "human"
    interaction_seed: Optional[int] = None


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
    model_config = ConfigDict(extra="forbid")
    include_snapshot_refs: bool = True


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
    timeout_ms: int = Field(default=5_000, ge=1000)


class ControlClickBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str
    timeout_ms: int = Field(default=5_000, ge=1000)


class ControlFillBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str
    text: str
    timeout_ms: int = Field(default=5_000, ge=1000)
    typing_delay_ms: Optional[int] = Field(default=None, ge=0)


class ControlPressBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str


class ControlWaitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selector: Optional[str] = None
    load_state: Optional[Literal["domcontentloaded", "networkidle"]] = None
    timeout_ms: int = Field(default=5_000, ge=1000)


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
    get_interaction_profile(ctx.interaction_profile)
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
        event_path = _write_session_event(
            runtime=runtime,
            session_id=sid,
            op="control.create_session",
            request=body,
            response=None,
            error={"kind": "capability_error", "detail": exc.to_dict()},
            meta={"transport": "http", "path": "/control/sessions"},
        )
        _write_console_sidecars(runtime=runtime, session_id=sid, event_path=event_path)
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
    event_path = _write_session_event(
        runtime=runtime,
        session_id=sid,
        op="control.create_session",
        request=body,
        response=out,
        error=None,
        meta={"transport": "http", "path": "/control/sessions"},
    )
    _write_console_sidecars(runtime=runtime, session_id=sid, event_path=event_path)
    return out


@router.post("/sessions/{session_id}/navigate")
async def control_navigate(
    session_id: str,
    body: ControlNavigateBody,
    container: ContainerDep,
) -> dict[str, Any]:
    runtime = container.browser_runtime
    async with runtime.lease_manager.session_navigate_exclusive(session_id):
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
            event_path = _write_session_event(
                runtime=runtime,
                session_id=session_id,
                op="control.navigate",
                request=body,
                response=None,
                error={"kind": "capability_error", "detail": exc.to_dict()},
                meta={"transport": "http", "path": f"/control/sessions/{session_id}/navigate"},
            )
            _write_console_sidecars(runtime=runtime, session_id=session_id, event_path=event_path)
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
        payload = {
            "final_url": out.final_url,
            "status_code": out.status_code,
            "response_headers": out.response_headers,
            "screenshot_ref": out.screenshot_ref,
            "pdf_ref": out.pdf_ref,
            "snapshot_ref": out.snapshot_ref,
            "anti_bot_signals": out.anti_bot_signals,
        }
        event_path = _write_session_event(
            runtime=runtime,
            session_id=session_id,
            op="control.navigate",
            request=body,
            response=payload,
            error=None,
            meta={"transport": "http", "path": f"/control/sessions/{session_id}/navigate"},
        )
        _write_console_sidecars(runtime=runtime, session_id=session_id, event_path=event_path)
        return payload


@router.post("/sessions/{session_id}/observe")
async def control_observe(
    session_id: str,
    body: ControlObserveBody,
    container: ContainerDep,
) -> dict[str, Any]:
    runtime = container.browser_runtime
    async with runtime.lease_manager.session_navigate_exclusive(session_id):
        try:
            page = await runtime.lease_manager.get_page_for_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        payload: dict[str, Any] = {"session_id": session_id, "url": page.url}

        # Observe должен работать на "готовой" странице: domcontentloaded достаточно.
        # `networkidle` на Lightpanda и на сайтах с трекерами может не наступать (или падать),
        # а observe не должен зависеть от аналитики/рекламы.
        await page.wait_for_load_state("domcontentloaded", timeout=10_000)

        # Каноничный LLM-friendly snapshot: строим строго через JS в странице (page.evaluate),
        # без зависимости от Playwright accessibility API и без тяжёлых «сырьевых» деревьев.
        ax = await dom_accessibility_tree_dict_from_page(page)
        snap_text, refs = build_interactive_snapshot_with_refs(ax)
        payload["snapshot"] = {
            "schema": "browser.control.snapshot.v1",
            "mode": "interactive",
            "text": snap_text,
        }
        runtime.observe_store.update_refs(session_id, refs)
        # if body.include_snapshot_refs:
        payload["snapshot"]["refs"] = refs

        event_path = _write_session_event(
            runtime=runtime,
            session_id=session_id,
            op="control.observe",
            request=body,
            response=payload,
            error=None,
            meta={"transport": "http", "path": f"/control/sessions/{session_id}/observe"},
        )
        _write_console_sidecars(runtime=runtime, session_id=session_id, event_path=event_path)
        html = await page.content()
        html_path = runtime.session_artifacts.write_sidecar_text_for_event(
            event_json_path=event_path,
            ext=".html",
            content=html,
        )
        runtime.session_artifacts.patch_event_meta(
            event_json_path=event_path,
            meta_patch={"html_ref": html_path},
        )

        page_err = _extract_page_error_from_html(html)
        if page_err is not None:
            page_err_path = runtime.session_artifacts.write_sidecar_text_for_event(
                event_json_path=event_path,
                ext=".page_error.json",
                content=json.dumps(page_err, ensure_ascii=False, indent=2),
            )
            runtime.session_artifacts.patch_event_meta(
                event_json_path=event_path,
                meta_patch={"page_error": page_err, "page_error_ref": page_err_path},
            )
        return payload


@router.post("/sessions/{session_id}/action")
async def control_action(
    session_id: str,
    body: ControlActionBody,
    container: ContainerDep,
) -> dict[str, Any]:
    runtime = container.browser_runtime
    async with runtime.lease_manager.session_navigate_exclusive(session_id):
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
            event_path = _write_session_event(
                runtime=runtime,
                session_id=session_id,
                op="control.action",
                request=body,
                response=out,
                error=None,
                meta={"transport": "http", "path": f"/control/sessions/{session_id}/action"},
            )
            _write_console_sidecars(runtime=runtime, session_id=session_id, event_path=event_path)
            return out
        except BrowserCapabilityError as exc:
            event_path = _write_session_event(
                runtime=runtime,
                session_id=session_id,
                op="control.action",
                request=body,
                response=None,
                error={"kind": "capability_error", "detail": exc.to_dict()},
                meta={"transport": "http", "path": f"/control/sessions/{session_id}/action"},
            )
            _write_console_sidecars(runtime=runtime, session_id=session_id, event_path=event_path)
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


def _interaction_for_session(runtime: Any, session_id: str) -> tuple[HumanInteraction, object, InteractionRng]:
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
) -> dict[str, Any]:
    runtime = container.browser_runtime
    async with runtime.lease_manager.session_navigate_exclusive(session_id):
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
        out = {"ok": True}
        event_path = _write_session_event(
            runtime=runtime,
            session_id=session_id,
            op="control.click",
            request=body,
            response=out,
            error=None,
            meta={"transport": "http", "path": f"/control/sessions/{session_id}/click"},
        )
        _write_console_sidecars(runtime=runtime, session_id=session_id, event_path=event_path)
        return out


@router.post("/sessions/{session_id}/fill")
async def control_fill(
    session_id: str,
    body: ControlFillBody,
    container: ContainerDep,
) -> dict[str, Any]:
    runtime = container.browser_runtime
    async with runtime.lease_manager.session_navigate_exclusive(session_id):
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
        out = {"ok": True}
        event_path = _write_session_event(
            runtime=runtime,
            session_id=session_id,
            op="control.fill",
            request=body,
            response=out,
            error=None,
            meta={"transport": "http", "path": f"/control/sessions/{session_id}/fill"},
        )
        _write_console_sidecars(runtime=runtime, session_id=session_id, event_path=event_path)
        return out


@router.post("/sessions/{session_id}/press")
async def control_press(
    session_id: str,
    body: ControlPressBody,
    container: ContainerDep,
) -> dict[str, Any]:
    runtime = container.browser_runtime
    async with runtime.lease_manager.session_navigate_exclusive(session_id):
        try:
            page = await runtime.lease_manager.get_page_for_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        inter, profile, rnd = _interaction_for_session(runtime, session_id)
        await inter.press(page, body.key, profile=profile, rnd=rnd)
        out = {"ok": True}
        event_path = _write_session_event(
            runtime=runtime,
            session_id=session_id,
            op="control.press",
            request=body,
            response=out,
            error=None,
            meta={"transport": "http", "path": f"/control/sessions/{session_id}/press"},
        )
        _write_console_sidecars(runtime=runtime, session_id=session_id, event_path=event_path)
        return out


@router.post("/sessions/{session_id}/wait")
async def control_wait(
    session_id: str,
    body: ControlWaitBody,
    container: ContainerDep,
) -> dict[str, Any]:
    runtime = container.browser_runtime
    async with runtime.lease_manager.session_navigate_exclusive(session_id):
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
        out = {"ok": True}
        event_path = _write_session_event(
            runtime=runtime,
            session_id=session_id,
            op="control.wait",
            request=body,
            response=out,
            error=None,
            meta={"transport": "http", "path": f"/control/sessions/{session_id}/wait"},
        )
        _write_console_sidecars(runtime=runtime, session_id=session_id, event_path=event_path)
        return out


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
    runtime.session_artifacts.forget(session_id)
    out = {"status": "closed"}
    event_path = _write_session_event(
        runtime=runtime,
        session_id=session_id,
        op="control.close_session",
        request={"session_id": session_id},
        response=out,
        error=None,
        meta={"transport": "http", "path": f"/control/sessions/{session_id}"},
    )
    _write_console_sidecars(runtime=runtime, session_id=session_id, event_path=event_path)
    return out
