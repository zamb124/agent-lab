"""Контекст и вызов reembed-задачи RAG worker."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_rag_reembed_task_sets_and_clears_system_context(monkeypatch) -> None:
    import apps.rag_worker.tasks.maintenance_tasks as maintenance_tasks

    class ProviderStub:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def _embedding_model_name(self) -> str:
            return "qwen/qwen3-embedding-0.6b"

        async def reembed_stale_documents(self, *, batch_size: int, target_embedding_model: str) -> int:
            self.calls.append(
                {
                    "batch_size": batch_size,
                    "target_embedding_model": target_embedding_model,
                }
            )
            return 5

    provider = ProviderStub()
    container = SimpleNamespace(rag_provider=provider)
    monkeypatch.setattr(maintenance_tasks, "get_rag_container", lambda: container)
    monkeypatch.setattr(
        maintenance_tasks,
        "get_settings",
        lambda: SimpleNamespace(
            rag=SimpleNamespace(
                ttl=SimpleNamespace(
                    reembed_enabled=True,
                    reembed_batch_size=13,
                )
            )
        ),
    )

    system_context = object()
    monkeypatch.setattr(
        maintenance_tasks,
        "build_system_auth_context",
        AsyncMock(return_value=system_context),
    )

    set_calls: list[object] = []
    clear_calls: list[str] = []
    monkeypatch.setattr(maintenance_tasks, "set_context", lambda ctx: set_calls.append(ctx))
    monkeypatch.setattr(maintenance_tasks, "clear_context", lambda: clear_calls.append("cleared"))

    result = await maintenance_tasks.rag_reembed_stale_documents_tick(scheduler_task_id="sched-1")

    assert set_calls == [system_context]
    assert clear_calls == ["cleared"]
    assert provider.calls == [
        {
            "batch_size": 13,
            "target_embedding_model": "qwen/qwen3-embedding-0.6b",
        }
    ]
    assert result == {
        "skipped": False,
        "scheduler_task_id": "sched-1",
        "target_embedding_model": "qwen/qwen3-embedding-0.6b",
        "batch_size": 13,
        "reembedded": 5,
    }
