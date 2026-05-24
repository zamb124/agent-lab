"""SQLite-реестр моделей provider_litserve."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Literal, Protocol, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from core.config.models import (
    ProviderLitserveInfraConfig,
    ProviderLitserveSTTModelEntry,
    ProviderLitserveTTSModelEntry,
    ProviderLitserveVADModelEntry,
)

ModelKind = Literal["embedding", "rerank", "stt", "tts", "vad"]
ModelStatus = Literal["pending", "downloading", "ready", "failed", "deleted"]


class RegistryModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    model_id: str
    kind: ModelKind
    hf_model_id: str
    api_model_id: str
    status: ModelStatus
    error: str | None
    created_at: str
    updated_at: str


class AudioModelEntry(Protocol):
    api_model_id: str
    hf_model_id: str


def _row_required_str(row: sqlite3.Row, column: str) -> str:
    value = cast(str | int | float | bytes | None, row[column])
    if isinstance(value, str):
        return value
    raise TypeError(f"models.{column} must be TEXT")


def _row_optional_str(row: sqlite3.Row, column: str) -> str | None:
    value = cast(str | int | float | bytes | None, row[column])
    if value is None or isinstance(value, str):
        return value
    raise TypeError(f"models.{column} must be TEXT or NULL")


def _row_required_int(row: sqlite3.Row, column: str) -> int:
    value = cast(str | int | float | bytes | None, row[column])
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"models.{column} must be INTEGER")
    return value


def _parse_model_kind(value: str) -> ModelKind:
    match value:
        case "embedding" | "rerank" | "stt" | "tts" | "vad":
            return value
        case _:
            raise ValueError(f"unsupported model kind in registry: {value}")


def _parse_model_status(value: str) -> ModelStatus:
    match value:
        case "pending" | "downloading" | "ready" | "failed" | "deleted":
            return value
        case _:
            raise ValueError(f"unsupported model status in registry: {value}")


def _registry_model_from_row(row: sqlite3.Row) -> RegistryModel:
    return RegistryModel(
        model_id=_row_required_str(row, "model_id"),
        kind=_parse_model_kind(_row_required_str(row, "kind")),
        hf_model_id=_row_required_str(row, "hf_model_id"),
        api_model_id=_row_required_str(row, "api_model_id"),
        status=_parse_model_status(_row_required_str(row, "status")),
        error=_row_optional_str(row, "error"),
        created_at=_row_required_str(row, "created_at"),
        updated_at=_row_required_str(row, "updated_at"),
    )


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


def _build_audio_api_pairs_from_entries(
    *,
    entries: Sequence[AudioModelEntry],
    default_api_model_id: str,
    kind_label: str,
) -> dict[str, str]:
    """Маппинг api-id -> hf-id для STT/TTS/VAD из списка Pydantic entries.

    Каждый ``entry`` — объект с полями ``api_model_id`` и ``hf_model_id``
    (`ProviderLitserveSTT/TTS/VADModelEntry`). Бросает ``ValueError`` при
    дубликатах api-id и при отсутствии ``default_api_model_id`` в списке
    (Zero-Guess).
    """
    out: dict[str, str] = {}
    seen_api_lower: set[str] = set()
    for entry in entries:
        api_id = entry.api_model_id.strip()
        hf_id = entry.hf_model_id.strip()
        if not api_id:
            raise ValueError(
                f"provider_litserve {kind_label}_models: пустой api_model_id в записи"
            )
        if not hf_id:
            raise ValueError(
                f"provider_litserve {kind_label}_models: пустой hf_model_id для api_model_id={api_id!r}"
            )
        api_lower = api_id.lower()
        if api_lower in seen_api_lower:
            raise ValueError(
                f"provider_litserve {kind_label}_models: дубликат api_model_id={api_id!r}"
            )
        seen_api_lower.add(api_lower)
        out[api_id] = hf_id

    default_normalized = default_api_model_id.strip()
    if not default_normalized:
        raise ValueError(
            f"provider_litserve {kind_label}_default_api_model_id не должен быть пустым"
        )
    if default_normalized.lower() not in seen_api_lower:
        message = (
            f"provider_litserve {kind_label}_default_api_model_id={default_normalized!r} "
            + f"отсутствует в {kind_label}_models"
        )
        raise ValueError(message)
    return out


def build_stt_api_pairs(cfg: ProviderLitserveInfraConfig) -> dict[str, str]:
    return _build_audio_api_pairs_from_entries(
        entries=list(cfg.stt_models),
        default_api_model_id=cfg.stt_default_api_model_id,
        kind_label="stt",
    )


def build_tts_api_pairs(cfg: ProviderLitserveInfraConfig) -> dict[str, str]:
    return _build_audio_api_pairs_from_entries(
        entries=list(cfg.tts_models),
        default_api_model_id=cfg.tts_default_api_model_id,
        kind_label="tts",
    )


def build_vad_api_pairs(cfg: ProviderLitserveInfraConfig) -> dict[str, str]:
    return _build_audio_api_pairs_from_entries(
        entries=list(cfg.vad_models),
        default_api_model_id=cfg.vad_default_api_model_id,
        kind_label="vad",
    )


def find_stt_entry(
    cfg: ProviderLitserveInfraConfig,
    api_model_id: str,
) -> ProviderLitserveSTTModelEntry | None:
    """Найти ``ProviderLitserveSTTModelEntry`` по api id (case-insensitive). ``None`` если нет."""
    needle = api_model_id.strip().lower()
    for entry in cfg.stt_models:
        if entry.api_model_id.strip().lower() == needle:
            return entry
    return None


def find_tts_entry(
    cfg: ProviderLitserveInfraConfig,
    api_model_id: str,
) -> ProviderLitserveTTSModelEntry | None:
    needle = api_model_id.strip().lower()
    for entry in cfg.tts_models:
        if entry.api_model_id.strip().lower() == needle:
            return entry
    return None


def find_vad_entry(
    cfg: ProviderLitserveInfraConfig,
    api_model_id: str,
) -> ProviderLitserveVADModelEntry | None:
    needle = api_model_id.strip().lower()
    for entry in cfg.vad_models:
        if entry.api_model_id.strip().lower() == needle:
            return entry
    return None


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
    _ = conn.execute("PRAGMA journal_mode=WAL")
    _ = conn.execute("PRAGMA foreign_keys=ON")
    return conn


_MODELS_TABLE_SQL = """
CREATE TABLE models (
    model_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('embedding', 'rerank', 'stt', 'tts', 'vad')),
    hf_model_id TEXT NOT NULL,
    api_model_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN ('pending', 'downloading', 'ready', 'failed', 'deleted')),
    error TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def _migrate_models_table_if_needed(conn: sqlite3.Connection) -> None:
    """Idempotent: если CHECK у таблицы не покрывает новые kind'ы, пересоздать."""
    row = cast(sqlite3.Row | None, conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='models'"
    ).fetchone())
    if row is None:
        return
    current_sql = _row_required_str(row, "sql")
    allowed_kinds = ("embedding", "rerank", "stt", "tts", "vad")
    if all(f"'{kind}'" in current_sql for kind in allowed_kinds) and "'llm'" not in current_sql:
        return
    _ = conn.execute("ALTER TABLE models RENAME TO models_old_pre_rag_audio")
    _ = conn.execute(_MODELS_TABLE_SQL)
    _ = conn.execute(
        """
        INSERT INTO models(model_id, kind, hf_model_id, api_model_id, status, error, created_at, updated_at)
        SELECT model_id, kind, hf_model_id, api_model_id, status, error, created_at, updated_at
        FROM models_old_pre_rag_audio
        WHERE kind IN ('embedding', 'rerank', 'stt', 'tts', 'vad')
        """
    )
    _ = conn.execute("DROP TABLE models_old_pre_rag_audio")


def init_registry(cfg: ProviderLitserveInfraConfig) -> None:
    with _connect(cfg) as conn:
        existing = cast(sqlite3.Row | None, conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='models'"
        ).fetchone())
        if existing is None:
            _ = conn.execute(_MODELS_TABLE_SQL)
        else:
            _migrate_models_table_if_needed(conn)
        _ = conn.execute(
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


def _default_seed_models(cfg: ProviderLitserveInfraConfig) -> list[tuple[ModelKind, str, str]]:
    seed_models: list[tuple[ModelKind, str, str]] = []

    embedding_pairs = build_embedding_api_pairs(cfg)
    seed_models.extend(
        ("embedding", hf_model_id, api_model_id) for api_model_id, hf_model_id in embedding_pairs.items()
    )

    rerank_pairs = build_rerank_api_pairs(cfg)
    seed_models.extend(
        ("rerank", hf_model_id, api_model_id) for api_model_id, hf_model_id in rerank_pairs.items()
    )

    stt_pairs = build_stt_api_pairs(cfg)
    seed_models.extend(
        ("stt", hf_model_id, api_model_id) for api_model_id, hf_model_id in stt_pairs.items()
    )

    tts_pairs = build_tts_api_pairs(cfg)
    seed_models.extend(
        ("tts", hf_model_id, api_model_id) for api_model_id, hf_model_id in tts_pairs.items()
    )

    vad_pairs = build_vad_api_pairs(cfg)
    seed_models.extend(
        ("vad", hf_model_id, api_model_id) for api_model_id, hf_model_id in vad_pairs.items()
    )

    return seed_models


def bootstrap_defaults_if_empty(cfg: ProviderLitserveInfraConfig) -> None:
    with _connect(cfg) as conn:
        row = cast(sqlite3.Row | None, conn.execute("SELECT COUNT(*) AS total FROM models").fetchone())
        if row is None:
            raise RuntimeError("model registry count query returned no row")
        if _row_required_int(row, "total") > 0:
            return
        created_at = _now_iso()
        seed_models = _default_seed_models(cfg)

        for kind, hf_model_id, api_model_id in seed_models:
            _ = conn.execute(
                """
                INSERT INTO models(model_id, kind, hf_model_id, api_model_id, status, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'ready', NULL, ?, ?)
                """,
                (str(uuid4()), kind, hf_model_id, api_model_id, created_at, created_at),
            )


def sync_defaults_from_config(cfg: ProviderLitserveInfraConfig) -> None:
    """Идемпотентно синхронизирует дефолтные модели из конфига в реестр."""
    now = _now_iso()
    seed_models = _default_seed_models(cfg)
    with _connect(cfg) as conn:
        for kind, hf_model_id, api_model_id in seed_models:
            row = cast(sqlite3.Row | None, conn.execute(
                """
                SELECT model_id, kind, hf_model_id
                FROM models
                WHERE api_model_id = ?
                """,
                (api_model_id,),
            ).fetchone())
            if row is None:
                _ = conn.execute(
                    """
                    INSERT INTO models(model_id, kind, hf_model_id, api_model_id, status, error, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'ready', NULL, ?, ?)
                    """,
                    (str(uuid4()), kind, hf_model_id, api_model_id, now, now),
                )
                continue
            model_kind = _parse_model_kind(_row_required_str(row, "kind"))
            current_hf_model_id = _row_required_str(row, "hf_model_id")
            if model_kind == kind and current_hf_model_id == hf_model_id:
                continue
            _ = conn.execute(
                """
                UPDATE models
                SET kind = ?, hf_model_id = ?, status = 'ready', error = NULL, updated_at = ?
                WHERE model_id = ?
                """,
                (kind, hf_model_id, now, _row_required_str(row, "model_id")),
            )


def list_models(cfg: ProviderLitserveInfraConfig) -> list[RegistryModel]:
    with _connect(cfg) as conn:
        rows = cast(Sequence[sqlite3.Row], conn.execute(
            """
            SELECT model_id, kind, hf_model_id, api_model_id, status, error, created_at, updated_at
            FROM models
            ORDER BY created_at DESC
            """
        ).fetchall())
    return [_registry_model_from_row(row) for row in rows]


def list_ready_active_models(cfg: ProviderLitserveInfraConfig) -> list[RegistryModel]:
    with _connect(cfg) as conn:
        rows = cast(Sequence[sqlite3.Row], conn.execute(
            """
            SELECT model_id, kind, hf_model_id, api_model_id, status, error, created_at, updated_at
            FROM models
            WHERE status = 'ready'
            ORDER BY created_at DESC
            """
        ).fetchall())
    return [_registry_model_from_row(row) for row in rows]


def create_or_replace_model(cfg: ProviderLitserveInfraConfig, *, kind: ModelKind, hf_model_id: str, api_model_id: str) -> RegistryModel:
    if not hf_model_id.strip():
        raise ValueError("hf_model_id is required")
    if not api_model_id.strip():
        raise ValueError("api_model_id is required")
    now = _now_iso()
    model_id = str(uuid4())
    with _connect(cfg) as conn:
        existing = cast(
            sqlite3.Row | None,
            conn.execute("SELECT model_id FROM models WHERE api_model_id = ?", (api_model_id.strip(),)).fetchone(),
        )
        if existing is None:
            _ = conn.execute(
                """
                INSERT INTO models(model_id, kind, hf_model_id, api_model_id, status, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', NULL, ?, ?)
                """,
                (model_id, kind, hf_model_id.strip(), api_model_id.strip(), now, now),
            )
        else:
            model_id = _row_required_str(existing, "model_id")
            _ = conn.execute(
                """
                UPDATE models
                SET kind = ?, hf_model_id = ?, status = 'pending', error = NULL, updated_at = ?
                WHERE model_id = ?
                """,
                (kind, hf_model_id.strip(), now, model_id),
            )
        row = cast(sqlite3.Row | None, conn.execute(
            """
            SELECT model_id, kind, hf_model_id, api_model_id, status, error, created_at, updated_at
            FROM models
            WHERE model_id = ?
            """,
            (model_id,),
        ).fetchone())
    if row is None:
        raise RuntimeError(f"model registry write did not return model row: {model_id}")
    return _registry_model_from_row(row)


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
        row = cast(sqlite3.Row | None, conn.execute(
            """
            SELECT model_id, kind, hf_model_id, api_model_id, status, error, created_at, updated_at
            FROM models
            WHERE model_id = ?
            """,
            (model_id,),
        ).fetchone())
    if row is None:
        raise ValueError(f"model not found: {model_id}")
    return _registry_model_from_row(row)
