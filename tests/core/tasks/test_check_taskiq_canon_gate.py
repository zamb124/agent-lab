"""Контракт CI-гейта scripts/check_taskiq_canon.py (статический скан)."""

from __future__ import annotations

from pathlib import Path

import scripts.check_taskiq_canon as canon


def test_scan_forbidden_passes_on_clean_repo() -> None:
    errors = canon._scan_forbidden()  # pyright: ignore[reportPrivateUsage]
    assert errors == []


def test_kiq_allowlist_covers_enqueue_and_scheduler() -> None:
    allow = canon.KIQ_ALLOWLIST
    assert "core/tasks/kicker.py" in allow
    assert "apps/scheduler/dispatch.py" in allow
    assert "core/scheduler/service.py" in allow
    assert "apps/flows/src/api/v1/evaluation.py" not in allow
    assert "apps/flows/realtime/evaluation_operations.py" not in allow
    assert "apps/flows_worker/evaluation_tasks.py" not in allow


def test_create_broker_allowlist_is_thin_brokers_only() -> None:
    allow = canon.CREATE_BROKER_ALLOWLIST
    assert "core/tasks/broker.py" in allow
    assert "apps/rag_worker/broker.py" in allow
    assert "apps/sync/realtime/broker.py" in allow
    # HTTP/services не создают брокеры
    assert "apps/rag/api/documents.py" not in allow
    assert "core/mail/enqueue.py" not in allow


def test_repo_root_points_to_platform() -> None:
    assert (Path(canon.REPO_ROOT) / "core" / "tasks" / "kicker.py").is_file()
