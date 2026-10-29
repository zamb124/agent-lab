from __future__ import annotations

import pytest

import apps.idle.tasks.platform_free_models_tasks as task_module


class _TaskDi:
    redis_client = object()


@pytest.mark.asyncio
async def test_platform_free_models_task_accepts_scheduler_payload(monkeypatch) -> None:
    calls: list[tuple[object, object]] = []
    settings = object()

    async def fake_refresh(
        redis_client: object,
        settings_obj: object,
    ) -> dict[str, object]:
        calls.append((redis_client, settings_obj))
        return {
            "count": 2,
            "providers": ["openrouter", "bothub"],
            "models": ["openrouter:a:free", "bothub:b:free"],
            "overlay_count": 1,
            "redis_ok": True,
        }

    monkeypatch.setattr(task_module, "get_settings", lambda: settings)
    monkeypatch.setattr(task_module, "refresh_platform_free_models_cache", fake_refresh)

    result = await task_module.refresh_platform_free_models_task(
        schedule_task_id="schedule-1",
        company_id="system",
        system_task="platform_free_models_background_sync",
        di=_TaskDi(),
    )

    assert result == {
        "count": 2,
        "providers": ["openrouter", "bothub"],
        "models": ["openrouter:a:free", "bothub:b:free"],
        "overlay_count": 1,
        "redis_ok": True,
    }
    assert calls == [
        (
            _TaskDi.redis_client,
            settings,
        )
    ]
