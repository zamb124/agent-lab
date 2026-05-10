"""Контекст и вызов reembed-задачи CRM worker."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.no_crm_http


@pytest.mark.asyncio
async def test_crm_reembed_task_sets_and_clears_system_context(monkeypatch) -> None:
    import apps.crm_worker.tasks.reembed_tasks as reembed_tasks

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
            return 7

    provider = ProviderStub()
    monkeypatch.setattr(reembed_tasks, "_build_crm_pgvector_provider", lambda: provider)
    monkeypatch.setattr(
        reembed_tasks,
        "get_settings",
        lambda: SimpleNamespace(
            rag=SimpleNamespace(
                ttl=SimpleNamespace(
                    reembed_enabled=True,
                    reembed_batch_size=9,
                )
            )
        ),
    )
    monkeypatch.setattr(reembed_tasks, "get_crm_container", lambda: object())

    system_context = object()
    monkeypatch.setattr(
        reembed_tasks,
        "build_system_auth_context",
        AsyncMock(return_value=system_context),
    )

    set_calls: list[object] = []
    clear_calls: list[str] = []
    monkeypatch.setattr(reembed_tasks, "set_context", lambda ctx: set_calls.append(ctx))
    monkeypatch.setattr(reembed_tasks, "clear_context", lambda: clear_calls.append("cleared"))

    result = await reembed_tasks.crm_reembed_stale_documents_tick(scheduler_task_id="sched-2")

    assert set_calls == [system_context]
    assert clear_calls == ["cleared"]
    assert provider.calls == [
        {
            "batch_size": 9,
            "target_embedding_model": "qwen/qwen3-embedding-0.6b",
        }
    ]
    assert result == {
        "skipped": False,
        "scheduler_task_id": "sched-2",
        "target_embedding_model": "qwen/qwen3-embedding-0.6b",
        "batch_size": 9,
        "reembedded": 7,
    }
