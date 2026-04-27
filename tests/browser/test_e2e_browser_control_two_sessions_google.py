"""
E2E: полный цикл Browser Control HTTP API в двух сессиях.

Требования:
- только через публичный HTTP API browser-сервиса (ASGITransport);
- две независимые control-сессии;
- реальные действия в браузере: открыть duckduckgo.com, заполнить поиск, дождаться результатов;
- артефакты по шагам в JSON.
"""

import importlib
import json
import os
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.xdist_group("browser_cdp")

URL = "https://duckduckgo.com/"
ACTION_TIMEOUT_MS = 10_000
WAIT_TIMEOUT_MS = 30_000


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


async def _step_observe(ac: AsyncClient, *, session_id: str, step_dir: Path, step: str) -> dict:
    response = await ac.post(
        f"/browser/api/v1/control/sessions/{session_id}/observe",
        json={
            "budget": 120,
            "include_snapshot_refs": True,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    _write_json(step_dir / f"{step}.observe.json", payload)
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
            query = "playwright cdp"
            for sid in (f"sess-google-1-{uid}", f"sess-google-2-{uid}"):
                step_dir = step_root / sid

                create_res = await ac.post(
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
                            "interaction_profile": "human",
                        },
                    },
                )
                assert create_res.status_code == 200, create_res.text
                _write_json(step_dir / "S00_create_session.json", create_res.json())

                nav_res = await ac.post(
                    f"/browser/api/v1/control/sessions/{sid}/navigate",
                    json={
                        "url": URL,
                        "wait_policy": "domcontentloaded",
                        "screenshot": True,
                        "snapshot": True,
                        "capture_pdf": False,
                        "navigation_timeout_ms": WAIT_TIMEOUT_MS,
                    },
                )
                assert nav_res.status_code == 200, nav_res.text
                nav = nav_res.json()
                _write_json(step_dir / "S01_navigate.json", nav)
                assert isinstance(nav.get("snapshot_ref"), str) and nav["snapshot_ref"]

                obs1 = await _step_observe(
                    ac,
                    session_id=sid,
                    step_dir=step_dir,
                    step="S02_observe_landing",
                )
                pick = _pick_searchbox_ref(obs1)
                pick["source_observe_step"] = "S02_observe_landing.observe.json"
                pick["input_text"] = query
                _write_json(step_dir / "S02a_pick_search_ref.json", pick)
                search_ref = pick["search_ref"]

                fill_req = {"ref": search_ref, "text": query, "timeout_ms": ACTION_TIMEOUT_MS}
                fill_res = await ac.post(
                    f"/browser/api/v1/control/sessions/{sid}/fill",
                    json=fill_req,
                )
                assert fill_res.status_code == 200, fill_res.text
                _write_json(
                    step_dir / "S03_fill_search.json",
                    {"request": fill_req, "response": fill_res.json()},
                )

                press_req = {"key": "Enter"}
                press_res = await ac.post(
                    f"/browser/api/v1/control/sessions/{sid}/press",
                    json=press_req,
                )
                assert press_res.status_code == 200, press_res.text
                _write_json(
                    step_dir / "S04_press_enter.json",
                    {"request": press_req, "response": press_res.json()},
                )

                wait_req = {
                    "load_state": "domcontentloaded",
                    "selector": "a[data-testid='result-title-a'], h2 a",
                    "timeout_ms": WAIT_TIMEOUT_MS,
                }
                wait_res = await ac.post(
                    f"/browser/api/v1/control/sessions/{sid}/wait",
                    json=wait_req,
                )
                assert wait_res.status_code == 200, wait_res.text
                _write_json(
                    step_dir / "S05_wait_results.json",
                    {"request": wait_req, "response": wait_res.json()},
                )

                await _step_observe(ac, session_id=sid, step_dir=step_dir, step="S06_observe_results")

                close_res = await ac.delete(f"/browser/api/v1/control/sessions/{sid}")
                assert close_res.status_code == 200, close_res.text
                _write_json(step_dir / "S99_close.json", close_res.json())
