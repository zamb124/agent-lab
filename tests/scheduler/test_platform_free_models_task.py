from __future__ import annotations

import pytest

import apps.idle_worker.tasks.platform_free_models_tasks as task_module


class _Container:
    redis_client = object()
    ai_model_catalog_repository = object()
    llm_model_score_repository = object()


@pytest.mark.asyncio
async def test_platform_free_models_task_accepts_scheduler_payload(monkeypatch) -> None:
    calls: list[tuple[object, object, object, object]] = []
    settings = object()

    async def fake_refresh(
        redis_client: object,
        settings_obj: object,
        model_catalog_repository: object,
        *,
        model_score_provider: object,
    ) -> dict[str, object]:
        calls.append((redis_client, settings_obj, model_catalog_repository, model_score_provider))
        return {
            "count": 2,
            "providers": ["openrouter", "bothub"],
            "models": ["openrouter:a:free", "bothub:b:free"],
            "score_overrides_count": 1,
            "redis_ok": True,
        }

    monkeypatch.setattr(task_module, "get_container", lambda: _Container())
    monkeypatch.setattr(task_module, "get_settings", lambda: settings)
    monkeypatch.setattr(task_module, "refresh_platform_free_models_cache", fake_refresh)

    result = await task_module.refresh_platform_free_models_task(
        schedule_task_id="schedule-1",
        company_id="system",
        system_task="platform_free_models_background_sync",
    )

    assert result == {
        "count": 2,
        "providers": ["openrouter", "bothub"],
        "models": ["openrouter:a:free", "bothub:b:free"],
        "score_overrides_count": 1,
        "redis_ok": True,
    }
    assert calls == [
        (
            _Container.redis_client,
            settings,
            _Container.ai_model_catalog_repository,
            _Container.llm_model_score_repository,
        )
    ]
