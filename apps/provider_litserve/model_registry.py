"""SQLite-реестр моделей provider_litserve."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Literal
from uuid import uuid4

from core.config.models import ProviderLitserveInfraConfig

ModelKind = Literal["llm", "embedding", "rerank"]
ModelStatus = Literal["pending", "downloading", "ready", "failed", "deleted"]


@dataclass(slots=True, frozen=True)
class RegistryModel:
    model_id: str
    kind: ModelKind
    hf_model_id: str
    api_model_id: str
    status: ModelStatus
    error: str | None
    created_at: str
    updated_at: str


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _api_key_norm(s: str) -> str:
    return s.strip().lower()


def build_embedding_api_pairs(cfg: ProviderLitserveInfraConfig) -> dict[str, str]:
    """
    OpenAI-имя model -> HF id для весов.
    Без дублей: не добавляем hf->hf, если уже есть алиас (api) на тот же hf;
    в embedding_model_ids не дублируем ключ, совпадающий с существующим по регистру.
    """
    out: dict[str, str] = {}
    hf = cfg.embedding_model_id.strip()
    api = cfg.embedding_openai_model_id.strip()
    if api:
        out[api] = hf
    if hf and not any(v.strip().lower() == hf.lower() for v in out.values()):
        out[hf] = hf
    for model_id in cfg.embedding_model_ids:
        n = model_id.strip()
        if not n:
            continue
        if n in out:
            continue
        if any(_api_key_norm(n) == _api_key_norm(k) for k in out):
            continue
        out[n] = n
    return out


def build_rerank_api_pairs(cfg: ProviderLitserveInfraConfig) -> dict[str, str]:
    out: dict[str, str] = {}
    hf = cfg.model_id.strip()
    api = cfg.rerank_openai_model_id.strip()
    if api:
        out[api] = hf
    if hf and not any(v.strip().lower() == hf.lower() for v in out.values()):
        out[hf] = hf
    for model_id in cfg.rerank_model_ids:
        n = model_id.strip()
        if not n:
            continue
        if n in out:
            continue
        if any(_api_key_norm(n) == _api_key_norm(k) for k in out):
            continue
        out[n] = n
    return out


def _db_path(cfg: ProviderLitserveInfraConfig) -> Path:
    db_path = Path(cfg.sqlite_path).expanduser()
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _connect(cfg: ProviderLitserveInfraConfig) -> sqlite3.Connection:
    path = _db_path(cfg)
    conn = sqlite3.connect(path, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_registry(cfg: ProviderLitserveInfraConfig) -> None:
    with _connect(cfg) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS models (
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
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS model_operations (
                operation_id TEXT PRIMARY KEY,
                model_id TEXT NOT NULL,
                operation TEXT NOT NULL CHECK(operation IN ('add', 'retry', 'delete', 'download')),
                status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'done', 'failed')),
                error TEXT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(model_id) REFERENCES models(model_id) ON DELETE CASCADE
            )
            """
        )


def bootstrap_defaults_if_empty(cfg: ProviderLitserveInfraConfig) -> None:
    with _connect(cfg) as conn:
        total = conn.execute("SELECT COUNT(*) AS total FROM models").fetchone()["total"]
        if int(total) > 0:
            return
        created_at = _now_iso()
        seed_models: list[tuple[ModelKind, str, str]] = []

        llm_ids = [item.strip() for item in cfg.llm_model_ids if item.strip()]
        if not llm_ids:
            llm_ids = [cfg.llm_model_id.strip()]
        seed_models.extend(("llm", model_id, model_id) for model_id in llm_ids if model_id)

        embedding_pairs = build_embedding_api_pairs(cfg)
        seed_models.extend(
            ("embedding", hf_model_id, api_model_id) for api_model_id, hf_model_id in embedding_pairs.items()
        )

        rerank_pairs = build_rerank_api_pairs(cfg)
        seed_models.extend(
            ("rerank", hf_model_id, api_model_id) for api_model_id, hf_model_id in rerank_pairs.items()
        )

        for kind, hf_model_id, api_model_id in seed_models:
            conn.execute(
                """
                INSERT INTO models(model_id, kind, hf_model_id, api_model_id, status, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'ready', NULL, ?, ?)
                """,
                (str(uuid4()), kind, hf_model_id, api_model_id, created_at, created_at),
            )


def list_models(cfg: ProviderLitserveInfraConfig) -> list[RegistryModel]:
    with _connect(cfg) as conn:
        rows = conn.execute(
            """
            SELECT model_id, kind, hf_model_id, api_model_id, status, error, created_at, updated_at
            FROM models
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [
        RegistryModel(
            model_id=row["model_id"],
            kind=row["kind"],
            hf_model_id=row["hf_model_id"],
            api_model_id=row["api_model_id"],
            status=row["status"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def list_ready_active_models(cfg: ProviderLitserveInfraConfig) -> list[RegistryModel]:
    with _connect(cfg) as conn:
        rows = conn.execute(
            """
            SELECT model_id, kind, hf_model_id, api_model_id, status, error, created_at, updated_at
            FROM models
            WHERE status = 'ready'
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [
        RegistryModel(
            model_id=row["model_id"],
            kind=row["kind"],
            hf_model_id=row["hf_model_id"],
            api_model_id=row["api_model_id"],
            status=row["status"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def create_or_replace_model(cfg: ProviderLitserveInfraConfig, *, kind: ModelKind, hf_model_id: str, api_model_id: str) -> RegistryModel:
    if not hf_model_id.strip():
        raise ValueError("hf_model_id is required")
    if not api_model_id.strip():
        raise ValueError("api_model_id is required")
    now = _now_iso()
    model_id = str(uuid4())
    with _connect(cfg) as conn:
        existing = conn.execute("SELECT model_id FROM models WHERE api_model_id = ?", (api_model_id.strip(),)).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO models(model_id, kind, hf_model_id, api_model_id, status, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', NULL, ?, ?)
                """,
                (model_id, kind, hf_model_id.strip(), api_model_id.strip(), now, now),
            )
        else:
            model_id = existing["model_id"]
            conn.execute(
                """
                UPDATE models
                SET kind = ?, hf_model_id = ?, status = 'pending', error = NULL, updated_at = ?
                WHERE model_id = ?
                """,
                (kind, hf_model_id.strip(), now, model_id),
            )
        row = conn.execute(
            """
            SELECT model_id, kind, hf_model_id, api_model_id, status, error, created_at, updated_at
            FROM models
            WHERE model_id = ?
            """,
            (model_id,),
        ).fetchone()
    return RegistryModel(
        model_id=row["model_id"],
        kind=row["kind"],
        hf_model_id=row["hf_model_id"],
        api_model_id=row["api_model_id"],
        status=row["status"],
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def mark_model_status(cfg: ProviderLitserveInfraConfig, *, model_id: str, status: ModelStatus, error: str | None = None) -> None:
    now = _now_iso()
    with _connect(cfg) as conn:
        updated = conn.execute(
            "UPDATE models SET status = ?, error = ?, updated_at = ? WHERE model_id = ?",
            (status, error, now, model_id),
        )
        if updated.rowcount == 0:
            raise ValueError(f"model not found: {model_id}")


def mark_model_deleted(cfg: ProviderLitserveInfraConfig, *, model_id: str) -> None:
    mark_model_status(cfg, model_id=model_id, status="deleted", error=None)


def get_model(cfg: ProviderLitserveInfraConfig, *, model_id: str) -> RegistryModel:
    with _connect(cfg) as conn:
        row = conn.execute(
            """
            SELECT model_id, kind, hf_model_id, api_model_id, status, error, created_at, updated_at
            FROM models
            WHERE model_id = ?
            """,
            (model_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"model not found: {model_id}")
    return RegistryModel(
        model_id=row["model_id"],
        kind=row["kind"],
        hf_model_id=row["hf_model_id"],
        api_model_id=row["api_model_id"],
        status=row["status"],
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
