"""init_registry мигрирует старую models-таблицу под аудио-kinds.

Создаём реальную SQLite-БД со старой схемой (CHECK без stt/tts/vad),
кладём строку, вызываем init_registry, проверяем что данные не утеряны
и новая схема разрешает stt/tts/vad.
"""

from __future__ import annotations

import sqlite3

import pytest

from apps.provider_litserve.model_registry import (
    create_or_replace_model,
    init_registry,
    list_models,
)
from core.config.models import ProviderLitserveInfraConfig


pytestmark = pytest.mark.timeout(15)


_OLD_SCHEMA_SQL = """
CREATE TABLE models (
    model_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('llm', 'embedding', 'rerank')),
    hf_model_id TEXT NOT NULL,
    api_model_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN ('pending', 'downloading', 'ready', 'failed', 'deleted')),
    error TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def _seed_old_models_db(path: str, unique_id: str) -> None:
    """Создаёт SQLite файл со старой схемой и одной legacy-строкой."""
    with sqlite3.connect(path) as conn:
        conn.execute(_OLD_SCHEMA_SQL)
        conn.execute(
            """
            INSERT INTO models(model_id, kind, hf_model_id, api_model_id, status, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                f"old-{unique_id}",
                "embedding",
                "BAAI/bge-m3",
                f"baai/bge-m3-{unique_id}",
                "ready",
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:00:00Z",
            ),
        )
    with sqlite3.connect(path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO models(model_id, kind, hf_model_id, api_model_id, status, error, created_at, updated_at)
                VALUES (?, 'stt', ?, ?, 'ready', NULL, ?, ?)
                """,
                (
                    f"will-fail-{unique_id}",
                    "ai-sage/GigaAM-v3",
                    f"gigaam-pre-{unique_id}",
                    "2024-01-01T00:00:00Z",
                    "2024-01-01T00:00:00Z",
                ),
            )


def test_init_registry_migrates_old_check_constraint(tmp_path, unique_id):
    db_path = str(tmp_path / f"old-{unique_id}.db")
    _seed_old_models_db(db_path, unique_id)
    cfg = ProviderLitserveInfraConfig(sqlite_path=db_path)

    init_registry(cfg)

    models_after = {m.api_model_id: m for m in list_models(cfg)}
    assert f"baai/bge-m3-{unique_id}" in models_after, "legacy строка должна сохраниться"
    assert models_after[f"baai/bge-m3-{unique_id}"].kind == "embedding"
    assert models_after[f"baai/bge-m3-{unique_id}"].hf_model_id == "BAAI/bge-m3"

    new_stt = create_or_replace_model(
        cfg,
        kind="stt",
        hf_model_id="ai-sage/GigaAM-v3",
        api_model_id=f"gigaam-{unique_id}",
    )
    assert new_stt.kind == "stt"

    with sqlite3.connect(db_path) as conn:
        old_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='models_old_pre_audio'"
        ).fetchone()
    assert old_table is None, "временная _old таблица должна быть удалена после миграции"


def test_init_registry_idempotent_on_already_migrated_table(tmp_path, unique_id):
    db_path = str(tmp_path / f"new-{unique_id}.db")
    cfg = ProviderLitserveInfraConfig(sqlite_path=db_path)

    init_registry(cfg)
    create_or_replace_model(
        cfg,
        kind="vad",
        hf_model_id="snakers4/silero-vad",
        api_model_id=f"silero-{unique_id}",
    )

    init_registry(cfg)

    by_api = {m.api_model_id: m for m in list_models(cfg)}
    assert by_api[f"silero-{unique_id}"].kind == "vad"
