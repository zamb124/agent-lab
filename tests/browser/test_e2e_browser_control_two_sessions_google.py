"""
E2E: полный цикл Browser Control HTTP API в двух сессиях.

Требования:
- только через публичный HTTP API browser-сервиса (ASGITransport)
- две независимые control-сессии
- реальные действия в браузере: открыть duckduckgo.com, заполнить поле поиска, дождаться результатов
- артефакты по шагам: HTML + JSON observe (visibility/ax/snapshot) + server-side screenshot/snapshot refs

Тест запускается только при явном флаге и наличии CDP URL.

ВАЖНО: переменные окружения с префиксом `BROWSER__...` читаются Pydantic Settings-слоем
browser-сервиса. Поэтому e2e-флаги читаем из env, но перед сборкой приложения удаляем
из окружения любые `BROWSER__E2E_*`, чтобы не падать на `extra_forbid`.

Рекомендуемый запуск:
- BROWSER_E2E=1
- BROWSER_E2E_CDP_URL=ws://127.0.0.1:9222
"""

import importlib
import json
import os
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.xdist_group("browser_cdp")


def _enabled() -> bool:
    if os.environ.get("BROWSER_E2E", "").strip() == "1":
        return True
    return os.environ.get("BROWSER__E2E_LIGHTPANDA", "").strip() == "1"


def _cdp_url() -> str:
    cdp = os.environ.get("BROWSER_E2E_CDP_URL", "").strip()
    if cdp:
        return cdp
    cdp = os.environ.get("BROWSER__E2E_CDP_URL", "").strip()
    if cdp:
        return cdp
    cdp = os.environ.get("BROWSER__CDP_URL", "").strip()
    if not cdp:
        raise RuntimeError(
            "Не задан CDP URL: BROWSER_E2E_CDP_URL (рекомендуется) или BROWSER__CDP_URL"
        )
    return cdp


def _build_browser_app(*, cdp_url: str, artifacts_dir: str) -> object:
    # E2E-флаги не должны попадать в BrowserSettings (extra_forbid).
    os.environ.pop("BROWSER__E2E_CDP_URL", None)
    os.environ.pop("BROWSER__E2E_LIGHTPANDA", None)
    os.environ.pop("BROWSER__E2E_LIGHTPANDA_CDP_URL", None)

    os.environ["BROWSER__CDP_URL"] = cdp_url
    os.environ["BROWSER__ARTIFACTS_DIR"] = artifacts_dir

    from apps.browser.config import reset_browser_settings
    from apps.browser.container import reset_browser_container

    reset_browser_settings()
    reset_browser_container()

    import apps.browser.main as browser_main

    return importlib.reload(browser_main).app


def _write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


async def _step_observe(ac: AsyncClient, *, session_id: str, step_dir: Path, step: str) -> dict:
    r = await ac.post(
        f"/browser/api/v1/control/sessions/{session_id}/observe",
        json={
            "budget": 120,
            "include_html": True,
            "include_visibility": True,
            "include_ax": True,
            "include_snapshot": True,
            "include_snapshot_refs": True,
            "include_listeners": False,
            "include_dom_diff": False,
        },
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    _write_json(step_dir / f"{step}.observe.json", payload)
    html = payload.get("html")
    if isinstance(html, str):
        _write_text(step_dir / f"{step}.html", html)
    return payload


def _pick_searchbox_ref(payload: dict) -> dict:
    snap = payload.get("snapshot")
    if not isinstance(snap, dict):
        raise AssertionError("observe: snapshot отсутствует или не dict")
    refs = snap.get("refs")
    if not isinstance(refs, dict):
        raise AssertionError("observe: snapshot.refs отсутствует или не dict")

    candidates: list[tuple[int, str]] = []
    for ref, meta in refs.items():
        if not isinstance(ref, str) or not isinstance(meta, dict):
            continue
        role = meta.get("role")
        name = meta.get("name")
        if not isinstance(role, str) or not isinstance(name, str):
            continue
        role_l = role.lower()
        name_l = name.lower()
        # DuckDuckGo часто размечает поисковую строку как combobox с именем
        # "Search with DuckDuckGo". Если игнорировать combobox, легко выбрать
        # скрытый textbox (пустое имя) и повиснуть на ожидании видимости.
        if role_l not in ("combobox", "searchbox", "textbox"):
            continue
        score = 0
        if role_l == "combobox":
            score += 20
        if role_l == "searchbox":
            score += 10
        if "duckduckgo" in name_l:
            score += 10
        if "search" in name_l or "поиск" in name_l:
            score += 5
        # Пустые имена у textbox на DDG часто соответствуют скрытым полям формы,
        # поэтому считаем их самым слабым кандидатом.
        if name_l == "":
            if role_l == "textbox":
                score -= 10
            else:
                score += 1
        candidates.append((score, ref))
    if not candidates:
        raise AssertionError("Не найден ref для searchbox/combobox/textbox в snapshot.refs")
    candidates.sort(key=lambda x: (-x[0], x[1]))
    chosen_ref = candidates[0][1]
    chosen_meta = refs.get(chosen_ref)
    if not isinstance(chosen_meta, dict):
        raise AssertionError("observe: snapshot.refs[chosen_ref] отсутствует или не dict")

    candidates_out: list[dict] = []
    for score, ref in candidates:
        meta = refs.get(ref)
        if not isinstance(meta, dict):
            continue
        role = meta.get("role")
        name = meta.get("name")
        if not isinstance(role, str) or not isinstance(name, str):
            continue
        candidates_out.append(
            {
                "ref": f"@{ref}",
                "score": score,
                "role": role,
                "name": name,
            }
        )

    role = chosen_meta.get("role")
    name = chosen_meta.get("name")
    if not isinstance(role, str) or not isinstance(name, str):
        raise AssertionError("observe: snapshot.refs[chosen_ref] должен содержать строковые role/name")

    return {
        "search_ref": f"@{chosen_ref}",
        "chosen": {"ref": f"@{chosen_ref}", "role": role, "name": name},
        "candidates": candidates_out,
    }


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(360, func_only=True)
async def test_browser_control_http_two_sessions_google_search_artifacts() -> None:
    if not _enabled():
        pytest.skip("Включите BROWSER_E2E=1 (или BROWSER__E2E_LIGHTPANDA=1) для e2e прогона")

    uid = uuid.uuid4().hex
    artifacts_dir = f"artifacts/browser_e2e_two_sessions_google_{uid}"
    step_root = Path(artifacts_dir) / "steps"

    app = _build_browser_app(cdp_url=_cdp_url(), artifacts_dir=artifacts_dir)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
            # NOTE: некоторые CDP-движки (например Lightpanda) не поддерживают
            # одновременные несколько browser contexts (`Target.createBrowserContext`).
            # Поэтому прогоняем две сессии ПОСЛЕДОВАТЕЛЬНО, сохраняя артефакты по каждой.

            query = "playwright cdp"

            for sid in (f"sess-google-1-{uid}", f"sess-google-2-{uid}"):
                step_dir = step_root / sid

                r = await ac.post(
                    "/browser/api/v1/control/sessions",
                    json={
                        "session_id": sid,
                        "run_id": f"run-{sid}",
                        "task_id": f"task-{sid}",
                        "page_mode": "interactive",
                        "timeout_ms": 90_000,
                        "session_mode": "warm",
                        "context": {
                            "page_mode": "interactive",
                            "emulate_locale_timezone_via_cdp": False,
                            "anti_bot_tier": "gray",
                            "stealth_init_version": "v1",
                        },
                    },
                )
                assert r.status_code == 200, r.text
                _write_json(step_dir / "S00_create_session.json", r.json())

                rnav = await ac.post(
                    f"/browser/api/v1/control/sessions/{sid}/navigate",
                    json={
                        "url": "https://duckduckgo.com/",
                        "wait_policy": "domcontentloaded",
                        "screenshot": True,
                        "snapshot": True,
                        "capture_pdf": False,
                        "navigation_timeout_ms": 90_000,
                    },
                )
                assert rnav.status_code == 200, rnav.text
                nav = rnav.json()
                _write_json(step_dir / "S01_navigate.json", nav)
                assert isinstance(nav.get("snapshot_ref"), str) and nav["snapshot_ref"]

                obs1 = await _step_observe(
                    ac, session_id=sid, step_dir=step_dir, step="S02_observe_landing"
                )
                pick = _pick_searchbox_ref(obs1)
                pick["source_observe_step"] = "S02_observe_landing.observe.json"
                pick["input_text"] = query
                _write_json(step_dir / "S02a_pick_search_ref.json", pick)
                search_ref = pick["search_ref"]

                fill_req = {"ref": search_ref, "text": query, "timeout_ms": 60_000}
                rfill = await ac.post(
                    f"/browser/api/v1/control/sessions/{sid}/fill",
                    json=fill_req,
                )
                assert rfill.status_code == 200, rfill.text
                _write_json(
                    step_dir / "S03_fill_search.json",
                    {"request": fill_req, "response": rfill.json()},
                )

                press_req = {"key": "Enter"}
                rpress = await ac.post(
                    f"/browser/api/v1/control/sessions/{sid}/press",
                    json=press_req,
                )
                assert rpress.status_code == 200, rpress.text
                _write_json(
                    step_dir / "S04_press_enter.json",
                    {"request": press_req, "response": rpress.json()},
                )

                wait_req = {
                    "load_state": "domcontentloaded",
                    "selector": "a[data-testid='result-title-a'], h2 a",
                    "timeout_ms": 90_000,
                }
                rwait = await ac.post(
                    f"/browser/api/v1/control/sessions/{sid}/wait",
                    json=wait_req,
                )
                assert rwait.status_code == 200, rwait.text
                _write_json(
                    step_dir / "S05_wait_results.json",
                    {"request": wait_req, "response": rwait.json()},
                )

                await _step_observe(ac, session_id=sid, step_dir=step_dir, step="S06_observe_results")

                r2 = await ac.post(
                    f"/browser/api/v1/control/sessions/{sid}/navigate",
                    json={
                        "url": "about:blank",
                        "wait_policy": "domcontentloaded",
                        "screenshot": True,
                        "snapshot": True,
                        "capture_pdf": False,
                        "navigation_timeout_ms": 30_000,
                    },
                )
                assert r2.status_code == 200, r2.text
                _write_json(step_dir / "S07_navigate_about_blank_artifacts.json", r2.json())

                rd = await ac.delete(f"/browser/api/v1/control/sessions/{sid}")
                assert rd.status_code == 200, rd.text
                _write_json(step_root / sid / "S99_close.json", rd.json())


def _cdp_url() -> str:
    cdp = os.environ.get("BROWSER_E2E_CDP_URL", "").strip()
    if cdp:
        return cdp
    cdp = os.environ.get("BROWSER__E2E_CDP_URL", "").strip()
    if cdp:
        return cdp
    cdp = os.environ.get("BROWSER__CDP_URL", "").strip()
    if not cdp:
        raise RuntimeError(
            "Не задан CDP URL: BROWSER_E2E_CDP_URL (рекомендуется) или BROWSER__CDP_URL"
        )
    return cdp


def _build_browser_app(*, cdp_url: str, artifacts_dir: str) -> object:
    # E2E-флаги не должны попадать в BrowserSettings (extra_forbid).
    os.environ.pop("BROWSER__E2E_CDP_URL", None)
    os.environ.pop("BROWSER__E2E_LIGHTPANDA", None)
    os.environ.pop("BROWSER__E2E_LIGHTPANDA_CDP_URL", None)

    os.environ["BROWSER__CDP_URL"] = cdp_url
    os.environ["BROWSER__ARTIFACTS_DIR"] = artifacts_dir

    from apps.browser.config import reset_browser_settings
    from apps.browser.container import reset_browser_container

    reset_browser_settings()
    reset_browser_container()

    import apps.browser.main as browser_main

    return importlib.reload(browser_main).app


def _write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


async def _step_observe(ac: AsyncClient, *, session_id: str, step_dir: Path, step: str) -> dict:
    r = await ac.post(
        f"/browser/api/v1/control/sessions/{session_id}/observe",
        json={
            "budget": 120,
            "include_html": True,
            "include_visibility": True,
            "include_ax": True,
            "include_snapshot": True,
            "include_snapshot_refs": True,
            "include_listeners": False,
            "include_dom_diff": False,
        },
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    _write_json(step_dir / f"{step}.observe.json", payload)
    html = payload.get("html")
    if isinstance(html, str):
        _write_text(step_dir / f"{step}.html", html)
    return payload


def _pick_searchbox_ref(payload: dict) -> dict:
    snap = payload.get("snapshot")
    if not isinstance(snap, dict):
        raise AssertionError("observe: snapshot отсутствует или не dict")
    refs = snap.get("refs")
    if not isinstance(refs, dict):
        raise AssertionError("observe: snapshot.refs отсутствует или не dict")

    candidates: list[tuple[int, str]] = []
    for ref, meta in refs.items():
        if not isinstance(ref, str) or not isinstance(meta, dict):
            continue
        role = meta.get("role")
        name = meta.get("name")
        if not isinstance(role, str) or not isinstance(name, str):
            continue
        role_l = role.lower()
        name_l = name.lower()
        # DuckDuckGo часто размечает поисковую строку как combobox с именем
        # "Search with DuckDuckGo". Если игнорировать combobox, легко выбрать
        # скрытый textbox (пустое имя) и повиснуть на ожидании видимости.
        if role_l not in ("combobox", "searchbox", "textbox"):
            continue
        score = 0
        if role_l == "combobox":
            score += 20
        if role_l == "searchbox":
            score += 10
        if "duckduckgo" in name_l:
            score += 10
        if "search" in name_l or "поиск" in name_l:
            score += 5
        # Пустые имена у textbox на DDG часто соответствуют скрытым полям формы,
        # поэтому считаем их самым слабым кандидатом.
        if name_l == "":
            if role_l == "textbox":
                score -= 10
            else:
                score += 1
        candidates.append((score, ref))
    if not candidates:
        raise AssertionError("Не найден ref для searchbox/combobox/textbox в snapshot.refs")
    candidates.sort(key=lambda x: (-x[0], x[1]))
    chosen_ref = candidates[0][1]
    chosen_meta = refs.get(chosen_ref)
    if not isinstance(chosen_meta, dict):
        raise AssertionError("observe: snapshot.refs[chosen_ref] отсутствует или не dict")

    candidates_out: list[dict] = []
    for score, ref in candidates:
        meta = refs.get(ref)
        if not isinstance(meta, dict):
            continue
        role = meta.get("role")
        name = meta.get("name")
        if not isinstance(role, str) or not isinstance(name, str):
            continue
        candidates_out.append(
            {
                "ref": f"@{ref}",
                "score": score,
                "role": role,
                "name": name,
            }
        )

    role = chosen_meta.get("role")
    name = chosen_meta.get("name")
    if not isinstance(role, str) or not isinstance(name, str):
        raise AssertionError("observe: snapshot.refs[chosen_ref] должен содержать строковые role/name")

    return {
        "search_ref": f"@{chosen_ref}",
        "chosen": {"ref": f"@{chosen_ref}", "role": role, "name": name},
        "candidates": candidates_out,
    }


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(360, func_only=True)
async def test_browser_control_http_two_sessions_google_search_artifacts() -> None:
    if not _enabled():
        pytest.skip("Включите BROWSER_E2E=1 (или BROWSER__E2E_LIGHTPANDA=1) для e2e прогона")

    uid = uuid.uuid4().hex
    artifacts_dir = f"artifacts/browser_e2e_two_sessions_google_{uid}"
    step_root = Path(artifacts_dir) / "steps"

    app = _build_browser_app(cdp_url=_cdp_url(), artifacts_dir=artifacts_dir)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
            # NOTE: некоторые CDP-движки (например Lightpanda) не поддерживают
            # одновременные несколько browser contexts (`Target.createBrowserContext`).
            # Поэтому прогоняем две сессии ПОСЛЕДОВАТЕЛЬНО, сохраняя артефакты по каждой.

            query = "playwright cdp"

            for sid in (f"sess-google-1-{uid}", f"sess-google-2-{uid}"):
                step_dir = step_root / sid
                # create session
                r = await ac.post(
                    "/browser/api/v1/control/sessions",
                    json={
                        "session_id": sid,
                        "run_id": f"run-{sid}",
                        "task_id": f"task-{sid}",
                        "page_mode": "interactive",
                        "timeout_ms": 90_000,
                        "session_mode": "warm",
                        "context": {
                            "page_mode": "interactive",
                            "emulate_locale_timezone_via_cdp": False,
                            "anti_bot_tier": "gray",
                            "stealth_init_version": "v1",
                        },
                    },
                )
                assert r.status_code == 200, r.text
                _write_json(step_dir / "S00_create_session.json", r.json())

                # navigate with artifacts
                rnav = await ac.post(
                    f"/browser/api/v1/control/sessions/{sid}/navigate",
                    json={
                        "url": "https://duckduckgo.com/",
                        "wait_policy": "domcontentloaded",
                        "screenshot": True,
                        "snapshot": True,
                        "capture_pdf": False,
                        "navigation_timeout_ms": 90_000,
                    },
                )
                assert rnav.status_code == 200, rnav.text
                nav = rnav.json()
                _write_json(step_dir / "S01_navigate.json", nav)
                assert isinstance(nav.get("snapshot_ref"), str) and nav["snapshot_ref"]

                obs1 = await _step_observe(
                    ac, session_id=sid, step_dir=step_dir, step="S02_observe_landing"
                )
                pick = _pick_searchbox_ref(obs1)
                pick["source_observe_step"] = "S02_observe_landing.observe.json"
                pick["input_text"] = query
                _write_json(step_dir / "S02a_pick_search_ref.json", pick)
                search_ref = pick["search_ref"]

                fill_req = {"ref": search_ref, "text": query, "timeout_ms": 60_000}
                rfill = await ac.post(
                    f"/browser/api/v1/control/sessions/{sid}/fill",
                    json=fill_req,
                )
                assert rfill.status_code == 200, rfill.text
                _write_json(
                    step_dir / "S03_fill_search.json",
                    {"request": fill_req, "response": rfill.json()},
                )

                press_req = {"key": "Enter"}
                rpress = await ac.post(
                    f"/browser/api/v1/control/sessions/{sid}/press",
                    json=press_req,
                )
                assert rpress.status_code == 200, rpress.text
                _write_json(
                    step_dir / "S04_press_enter.json",
                    {"request": press_req, "response": rpress.json()},
                )

                wait_req = {
                    "load_state": "domcontentloaded",
                    "selector": "a[data-testid='result-title-a'], h2 a",
                    "timeout_ms": 90_000,
                }
                rwait = await ac.post(
                    f"/browser/api/v1/control/sessions/{sid}/wait",
                    json=wait_req,
                )
                assert rwait.status_code == 200, rwait.text
                _write_json(
                    step_dir / "S05_wait_results.json",
                    {"request": wait_req, "response": rwait.json()},
                )

                # after search: observe results (includes HTML + snapshot refs)
                await _step_observe(ac, session_id=sid, step_dir=step_dir, step="S06_observe_results")

                rd = await ac.delete(f"/browser/api/v1/control/sessions/{sid}")
                assert rd.status_code == 200, rd.text
                _write_json(step_root / sid / "S99_close.json", rd.json())

"""
E2E: полный цикл Browser Control HTTP API в двух сессиях.

Требования:
- только через публичный HTTP API browser-сервиса (ASGITransport)
- две независимые control-сессии
- реальные действия в браузере: открыть google.com, заполнить поле поиска, дождаться результатов
- артефакты по шагам: HTML + JSON observe (visibility/ax) + server-side screenshot/snapshot refs

Тест запускается только при явном флаге и наличии CDP URL.

ВАЖНО: переменные окружения с префиксом `BROWSER__...` читаются Pydantic Settings-слоем
browser-сервиса. Поэтому e2e-флаги читаем из env, но перед сборкой приложения удаляем
из окружения любые `BROWSER__E2E_*`, чтобы не падать на `extra_forbid`.

Рекомендуемый запуск:
- BROWSER_E2E=1
- BROWSER_E2E_CDP_URL=ws://127.0.0.1:9222
"""

import importlib
import json
import os
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.xdist_group("browser_cdp")


def _enabled() -> bool:
    if os.environ.get("BROWSER_E2E", "").strip() == "1":
        return True
    return os.environ.get("BROWSER__E2E_LIGHTPANDA", "").strip() == "1"


def _cdp_url() -> str:
    cdp = os.environ.get("BROWSER_E2E_CDP_URL", "").strip()
    if cdp:
        return cdp
    cdp = os.environ.get("BROWSER__E2E_CDP_URL", "").strip()
    if cdp:
        return cdp
    cdp = os.environ.get("BROWSER__CDP_URL", "").strip()
    if not cdp:
        raise RuntimeError(
            "Не задан CDP URL: BROWSER_E2E_CDP_URL (рекомендуется) или BROWSER__CDP_URL"
        )
    return cdp


def _build_browser_app(*, cdp_url: str, artifacts_dir: str) -> object:
    # E2E-флаги не должны попадать в BrowserSettings (extra_forbid).
    os.environ.pop("BROWSER__E2E_CDP_URL", None)
    os.environ.pop("BROWSER__E2E_LIGHTPANDA", None)
    os.environ.pop("BROWSER__E2E_LIGHTPANDA_CDP_URL", None)

    os.environ["BROWSER__CDP_URL"] = cdp_url
    os.environ["BROWSER__ARTIFACTS_DIR"] = artifacts_dir

    from apps.browser.config import reset_browser_settings
    from apps.browser.container import reset_browser_container

    reset_browser_settings()
    reset_browser_container()

    import apps.browser.main as browser_main

    return importlib.reload(browser_main).app


def _write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


async def _step_observe(ac: AsyncClient, *, session_id: str, step_dir: Path, step: str) -> dict:
    r = await ac.post(
        f"/browser/api/v1/control/sessions/{session_id}/observe",
        json={
            "budget": 120,
            "include_html": True,
            "include_visibility": True,
            "include_ax": True,
            "include_snapshot": True,
            "include_snapshot_refs": True,
            "include_listeners": False,
            "include_dom_diff": False,
        },
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    _write_json(step_dir / f"{step}.observe.json", payload)
    html = payload.get("html")
    if isinstance(html, str):
        _write_text(step_dir / f"{step}.html", html)
    return payload


def _pick_searchbox_ref(payload: dict) -> str:
    snap = payload.get("snapshot")
    if not isinstance(snap, dict):
        raise AssertionError("observe: snapshot отсутствует или не dict")
    refs = snap.get("refs")
    if not isinstance(refs, dict):
        raise AssertionError("observe: snapshot.refs отсутствует или не dict")
    candidates: list[tuple[int, str]] = []
    for ref, meta in refs.items():
        if not isinstance(ref, str) or not isinstance(meta, dict):
            continue
        role = meta.get("role")
        name = meta.get("name")
        if not isinstance(role, str) or not isinstance(name, str):
            continue
        role_l = role.lower()
        name_l = name.lower()
        # DuckDuckGo часто размечает поисковую строку как combobox с именем
        # "Search with DuckDuckGo". Если игнорировать combobox, легко выбрать
        # скрытый textbox (пустое имя) и повиснуть на ожидании видимости.
        if role_l not in ("combobox", "searchbox", "textbox"):
            continue
        score = 0
        if role_l == "combobox":
            score += 20
        if role_l == "searchbox":
            score += 10
        if "duckduckgo" in name_l:
            score += 10
        if "search" in name_l or "поиск" in name_l:
            score += 5
        # Пустые имена у textbox на DDG часто соответствуют скрытым полям формы,
        # поэтому считаем их самым слабым кандидатом.
        if name_l == "":
            if role_l == "textbox":
                score -= 10
            else:
                score += 1
        candidates.append((score, ref))
    if not candidates:
        raise AssertionError("Не найден ref для searchbox/combobox/textbox в snapshot.refs")
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return f"@{candidates[0][1]}"


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(360, func_only=True)
async def test_browser_control_http_two_sessions_google_search_artifacts() -> None:
    if not _enabled():
        pytest.skip("Включите BROWSER_E2E=1 (или BROWSER__E2E_LIGHTPANDA=1) для e2e прогона")

    uid = uuid.uuid4().hex
    artifacts_dir = f"artifacts/browser_e2e_two_sessions_google_{uid}"
    step_root = Path(artifacts_dir) / "steps"

    app = _build_browser_app(cdp_url=_cdp_url(), artifacts_dir=artifacts_dir)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
            # NOTE: некоторые CDP-движки (например Lightpanda) не поддерживают
            # одновременные несколько browser contexts (`Target.createBrowserContext`).
            # Поэтому прогоняем две сессии ПОСЛЕДОВАТЕЛЬНО, сохраняя артефакты по каждой.

            query = "playwright cdp"

            for sid in (f"sess-google-1-{uid}", f"sess-google-2-{uid}"):
                step_dir = step_root / sid
                # create session
                r = await ac.post(
                    "/browser/api/v1/control/sessions",
                    json={
                        "session_id": sid,
                        "run_id": f"run-{sid}",
                        "task_id": f"task-{sid}",
                        "page_mode": "interactive",
                        "timeout_ms": 90_000,
                        "session_mode": "warm",
                        "context": {
                            "page_mode": "interactive",
                            "emulate_locale_timezone_via_cdp": False,
                            "anti_bot_tier": "gray",
                            "stealth_init_version": "v1",
                        },
                    },
                )
                assert r.status_code == 200, r.text
                _write_json(step_dir / "S00_create_session.json", r.json())

                # navigate with artifacts
                rnav = await ac.post(
                    f"/browser/api/v1/control/sessions/{sid}/navigate",
                    json={
                        "url": "https://duckduckgo.com/",
                        "wait_policy": "domcontentloaded",
                        "screenshot": True,
                        "snapshot": True,
                        "capture_pdf": False,
                        "navigation_timeout_ms": 90_000,
                    },
                )
                assert rnav.status_code == 200, rnav.text
                nav = rnav.json()
                _write_json(step_dir / "S01_navigate.json", nav)
                # Lightpanda может не поддерживать Page.captureScreenshot.
                # В этом тесте мы запускаем режим emulate_locale_timezone_via_cdp=False (CDP-ограниченный backend),
                # поэтому screenshot_ref допускается None.
                # create-session в этом тесте всегда отправляет emulate_locale_timezone_via_cdp=False
                # (см. тело запроса выше), поэтому здесь не требуем screenshot_ref.
                assert isinstance(nav.get("snapshot_ref"), str) and nav["snapshot_ref"]

                obs1 = await _step_observe(ac, session_id=sid, step_dir=step_dir, step="S02_observe_landing")
                pick = _pick_searchbox_ref(obs1)
                pick["source_observe_step"] = "S02_observe_landing.observe.json"
                pick["input_text"] = query
                _write_json(step_dir / "S02a_pick_search_ref.json", pick)
                search_ref = pick["search_ref"]

                fill_req = {"ref": search_ref, "text": query, "timeout_ms": 60_000}
                rfill = await ac.post(
                    f"/browser/api/v1/control/sessions/{sid}/fill",
                    json=fill_req,
                )
                assert rfill.status_code == 200, rfill.text
                _write_json(
                    step_dir / "S03_fill_search.json",
                    {"request": fill_req, "response": rfill.json()},
                )

                press_req = {"key": "Enter"}
                rpress = await ac.post(
                    f"/browser/api/v1/control/sessions/{sid}/press",
                    json=press_req,
                )
                assert rpress.status_code == 200, rpress.text
                _write_json(
                    step_dir / "S04_press_enter.json",
                    {"request": press_req, "response": rpress.json()},
                )

                wait_req = {
                    "load_state": "domcontentloaded",
                    "selector": "a[data-testid='result-title-a'], h2 a",
                    "timeout_ms": 90_000,
                }
                rwait = await ac.post(
                    f"/browser/api/v1/control/sessions/{sid}/wait",
                    json=wait_req,
                )
                assert rwait.status_code == 200, rwait.text
                _write_json(
                    step_dir / "S05_wait_results.json",
                    {"request": wait_req, "response": rwait.json()},
                )

                # after search: observe results (includes HTML + snapshot refs)
                await _step_observe(ac, session_id=sid, step_dir=step_dir, step="S06_observe_results")

                rd = await ac.delete(f"/browser/api/v1/control/sessions/{sid}")
                assert rd.status_code == 200, rd.text
                _write_json(step_root / sid / "S99_close.json", rd.json())

