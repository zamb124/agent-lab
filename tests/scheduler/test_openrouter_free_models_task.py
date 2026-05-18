from __future__ import annotations

import pytest

import apps.idle_worker.tasks.openrouter_free_models_tasks as task_module


class _Container:
    redis_client = object()


@pytest.mark.asyncio
async def test_openrouter_free_models_task_accepts_scheduler_payload(monkeypatch) -> None:
    calls: list[tuple[object, object]] = []
    settings = object()

    async def fake_refresh(redis_client: object, settings_obj: object) -> dict[str, object]:
        calls.append((redis_client, settings_obj))
        return {"count": 2, "models": ["a:free", "b:free"], "redis_ok": True}

    monkeypatch.setattr(task_module, "get_container", lambda: _Container())
    monkeypatch.setattr(task_module, "get_settings", lambda: settings)
    monkeypatch.setattr(task_module, "refresh_openrouter_free_models_cache", fake_refresh)

    result = await task_module.refresh_openrouter_free_models_task(
        scheduler_task_id="schedule-1",
        company_id="system",
        system_task="openrouter_free_models_background_sync",
    )

    assert result == {"count": 2, "models": ["a:free", "b:free"], "redis_ok": True}
    assert calls == [(_Container.redis_client, settings)]
