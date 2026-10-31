"""Каталог локальных моделей provider_litserve — единственный источник желаемого состояния.

Таблица ``provider_litserve_models`` в ``platform_shared`` (``__global_model__``):
конфиг ``provider_litserve.infra`` — только seed при старте пода; дальше истина
живёт здесь. Под материализует ``ready``-строки в boot-time каталог воркеров
(LitServe spawn-воркеры получают снимок через pickle LitAPI и не читают БД).
Резолверы платформы (voice_resolver, каталог провайдеров речи, settings-UI)
читают те же строки через ``litserve_catalog_entries`` с TTL-кэшем.

Статусная машина — очередь операций одного пода: ``pending`` → download →
``ready``/``failed``; ``deleting`` → удаление весов → ``deleted`` (tombstone,
seed не воскрешает). Новые ``ready``-модели обслуживаются после рестарта пода.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import ClassVar, Literal, Self, TypeAlias
from uuid import uuid4

from oxyde import Field as DbField
from pydantic import BaseModel, ConfigDict, Field

from core.config.models import (
    ProviderLitserveSTTModelEntry,
    ProviderLitserveTTSModelEntry,
    ProviderLitserveVADModelEntry,
)
from core.models.platform_model import PlatformModel
from core.types import JsonObject

LitserveModelKind = Literal["embedding", "rerank", "stt", "tts", "vad"]
LitserveModelStatus = Literal[
    "pending", "downloading", "ready", "failed", "deleting", "deleted"
]

LITSERVE_MODEL_KINDS: tuple[LitserveModelKind, ...] = (
    "embedding",
    "rerank",
    "stt",
    "tts",
    "vad",
)


class ProviderLitserveModelPair(BaseModel):
    """Каталожная запись embedding/rerank-модели (пара api id ↔ HF id + опциональные метаданные)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    api_model_id: str
    hf_model_id: str
    revision: str | None = None
    dimension: int | None = None
    context_length: int | None = None


LitserveCatalogEntry: TypeAlias = (
    ProviderLitserveModelPair
    | ProviderLitserveSTTModelEntry
    | ProviderLitserveTTSModelEntry
    | ProviderLitserveVADModelEntry
)

_ENTRY_MODEL_BY_KIND: dict[LitserveModelKind, type[BaseModel]] = {
    "embedding": ProviderLitserveModelPair,
    "rerank": ProviderLitserveModelPair,
    "stt": ProviderLitserveSTTModelEntry,
    "tts": ProviderLitserveTTSModelEntry,
    "vad": ProviderLitserveVADModelEntry,
}


def litserve_entry_params(entry: LitserveCatalogEntry) -> JsonObject:
    """JSONB ``params`` строки: поля записи сверх api_model_id/hf_model_id."""
    payload: JsonObject = entry.model_dump(mode="json", exclude={"api_model_id", "hf_model_id"})
    return {key: value for key, value in payload.items() if value is not None}


def build_litserve_entry(
    *,
    kind: LitserveModelKind,
    api_model_id: str,
    hf_model_id: str,
    params: JsonObject | None = None,
) -> LitserveCatalogEntry:
    """Типизированная запись каталога для kind; ``ValueError`` при невалидных params."""
    entry_type = _ENTRY_MODEL_BY_KIND[kind]
    validated = entry_type.model_validate(
        {
            "api_model_id": api_model_id,
            "hf_model_id": hf_model_id,
            **(params or {}),
        }
    )
    if not isinstance(
        validated,
        ProviderLitserveModelPair
        | ProviderLitserveSTTModelEntry
        | ProviderLitserveTTSModelEntry
        | ProviderLitserveVADModelEntry,
    ):
        raise TypeError(
            f"provider_litserve entry for kind={kind} produced {type(validated).__name__}"
        )
    return validated


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProviderLitserveModel(PlatformModel):
    """Строка желаемого состояния одной локальной модели provider_litserve."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    model_id: str = DbField(default="", db_pk=True)

    class Meta:
        is_table: bool = True
        table_name: str = "provider_litserve_models"

    kind: LitserveModelKind = DbField(db_index=True)
    api_model_id: str = DbField(db_index=True, db_unique=True)
    hf_model_id: str
    status: LitserveModelStatus = DbField(default="pending", db_index=True)
    error: str | None = DbField(default=None)
    params: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    created_at: datetime = DbField(default_factory=_utcnow, db_index=True)
    updated_at: datetime = DbField(default_factory=_utcnow)

    def to_entry(self) -> LitserveCatalogEntry:
        """Типизированная запись каталога для kind (params → entry-модель)."""
        return build_litserve_entry(
            kind=self.kind,
            api_model_id=self.api_model_id,
            hf_model_id=self.hf_model_id,
            params=self.params,
        )

    @classmethod
    async def require(cls, model_id: str) -> Self:
        row = await cls.get(model_id)
        if row is None:
            raise ValueError(f"provider_litserve_models: model not found: {model_id}")
        return row

    @classmethod
    async def by_api_model_id(cls, api_model_id: str) -> Self | None:
        return await cls.objects.filter(api_model_id=api_model_id).get_or_none()

    @classmethod
    async def list_ready_by_created_at_asc(cls) -> list[Self]:
        """Все ready-строки по created_at ASC — детерминированный boot-time каталог."""
        return await cls.objects.filter(status="ready").order_by("created_at").all()

    @classmethod
    async def list_by_created_at_desc(cls) -> list[Self]:
        """Все строки для админ-списка, ORDER BY created_at DESC. Предела нет."""
        return await cls.objects.order_by("-created_at").all()

    @classmethod
    async def upsert_seed(
        cls,
        *,
        kind: LitserveModelKind,
        entry: LitserveCatalogEntry,
    ) -> Self | None:
        """Seed из конфига: вставка ready или обновление полей; tombstone ``deleted`` не трогает."""
        api_model_id = entry.api_model_id.strip()
        hf_model_id = entry.hf_model_id.strip()
        if not api_model_id or not hf_model_id:
            raise ValueError(
                f"provider_litserve seed: empty api_model_id/hf_model_id for kind={kind}"
            )
        params = litserve_entry_params(entry)
        now = _utcnow()
        existing = await cls.by_api_model_id(api_model_id)
        if existing is None:
            return await cls.objects.create(
                instance=cls(
                    model_id=str(uuid4()),
                    kind=kind,
                    api_model_id=api_model_id,
                    hf_model_id=hf_model_id,
                    status="ready",
                    params=params,
                    created_at=now,
                    updated_at=now,
                )
            )
        if existing.status == "deleted":
            return None
        if (
            existing.kind == kind
            and existing.hf_model_id == hf_model_id
            and existing.params == params
            and existing.status == "ready"
        ):
            return existing
        existing.kind = kind
        existing.hf_model_id = hf_model_id
        existing.params = params
        existing.status = "ready"
        existing.error = None
        existing.updated_at = now
        _ = await existing.save()
        return existing

    @classmethod
    async def create_or_replace(
        cls,
        *,
        kind: LitserveModelKind,
        entry: LitserveCatalogEntry,
    ) -> Self:
        """Админ-добавление: новая строка ``pending`` или сброс существующей в ``pending``."""
        api_model_id = entry.api_model_id.strip()
        hf_model_id = entry.hf_model_id.strip()
        if not api_model_id or not hf_model_id:
            raise ValueError("hf_model_id and api_model_id are required")
        params = litserve_entry_params(entry)
        now = _utcnow()
        existing = await cls.by_api_model_id(api_model_id)
        if existing is None:
            return await cls.objects.create(
                instance=cls(
                    model_id=str(uuid4()),
                    kind=kind,
                    api_model_id=api_model_id,
                    hf_model_id=hf_model_id,
                    status="pending",
                    params=params,
                    created_at=now,
                    updated_at=now,
                )
            )
        existing.kind = kind
        existing.hf_model_id = hf_model_id
        existing.params = params
        existing.status = "pending"
        existing.error = None
        existing.updated_at = now
        _ = await existing.save()
        return existing

    @classmethod
    async def mark_status(
        cls,
        *,
        model_id: str,
        status: LitserveModelStatus,
        error: str | None = None,
    ) -> Self:
        row = await cls.require(model_id)
        row.status = status
        row.error = error
        row.updated_at = _utcnow()
        _ = await row.save()
        return row

    @classmethod
    async def mark_ready_if_downloading(cls, *, model_id: str) -> Self | None:
        """Завершить скачивание; ``None`` если строка ушла из ``downloading`` (удаление и т.п.)."""
        now = _utcnow()
        affected = await cls.objects.filter(
            model_id=model_id, status="downloading"
        ).update(status="ready", error=None, updated_at=now)
        if affected == 0:
            return None
        return await cls.require(model_id)

    @classmethod
    async def claim_next_pending_download_by_created_at_asc(cls) -> Self | None:
        """Самая старая ``pending`` → ``downloading``. ``None`` — очередь пуста."""
        rows = (
            await cls.objects.filter(status="pending")
            .order_by("created_at")
            .limit(1)
            .all()
        )
        if not rows:
            return None
        row = rows[0]
        affected = await cls.objects.filter(
            model_id=row.model_id, status="pending"
        ).update(status="downloading", updated_at=_utcnow())
        if affected == 0:
            return None
        return await cls.require(row.model_id)

    @classmethod
    async def claim_next_deleting_by_created_at_asc(cls) -> Self | None:
        """Самая старая ``deleting``-строка. ``None`` — очередь пуста."""
        rows = (
            await cls.objects.filter(status="deleting")
            .order_by("created_at")
            .limit(1)
            .all()
        )
        if not rows:
            return None
        return rows[0]

    @classmethod
    async def reset_downloading_to_pending(cls) -> int:
        """Crash-recovery при старте ops-цикла: недокачанные обратно в очередь."""
        return await cls.objects.filter(status="downloading").update(
            status="pending", updated_at=_utcnow()
        )


class ProviderLitserveCatalogEntries(BaseModel):
    """Снимок ready-каталога по kind для резолверов платформы (DTO, voice_resolver)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

    embedding: tuple[ProviderLitserveModelPair, ...] = Field(default_factory=tuple)
    rerank: tuple[ProviderLitserveModelPair, ...] = Field(default_factory=tuple)
    stt: tuple[ProviderLitserveSTTModelEntry, ...] = Field(default_factory=tuple)
    tts: tuple[ProviderLitserveTTSModelEntry, ...] = Field(default_factory=tuple)
    vad: tuple[ProviderLitserveVADModelEntry, ...] = Field(default_factory=tuple)


_CATALOG_CACHE_TTL_S: float = 60.0
_catalog_cache: tuple[float, ProviderLitserveCatalogEntries] | None = None


def reset_litserve_catalog_cache_for_tests() -> None:
    """Сброс TTL-кэша каталога. Только для тестовой инфраструктуры."""
    global _catalog_cache
    _catalog_cache = None


async def litserve_catalog_entries() -> ProviderLitserveCatalogEntries:
    """Ready-строки каталога по kind, TTL-кэш процесса (как ``_load_company_override``)."""
    global _catalog_cache
    now = time.monotonic()
    if _catalog_cache is not None and (now - _catalog_cache[0]) < _CATALOG_CACHE_TTL_S:
        return _catalog_cache[1]

    grouped: dict[LitserveModelKind, list[LitserveCatalogEntry]] = {
        kind: [] for kind in LITSERVE_MODEL_KINDS
    }
    for row in await ProviderLitserveModel.list_ready_by_created_at_asc():
        grouped[row.kind].append(row.to_entry())

    def _pairs(kind: LitserveModelKind) -> tuple[ProviderLitserveModelPair, ...]:
        return tuple(
            entry for entry in grouped[kind] if isinstance(entry, ProviderLitserveModelPair)
        )

    def _stt() -> tuple[ProviderLitserveSTTModelEntry, ...]:
        return tuple(
            entry
            for entry in grouped["stt"]
            if isinstance(entry, ProviderLitserveSTTModelEntry)
        )

    def _tts() -> tuple[ProviderLitserveTTSModelEntry, ...]:
        return tuple(
            entry
            for entry in grouped["tts"]
            if isinstance(entry, ProviderLitserveTTSModelEntry)
        )

    def _vad() -> tuple[ProviderLitserveVADModelEntry, ...]:
        return tuple(
            entry
            for entry in grouped["vad"]
            if isinstance(entry, ProviderLitserveVADModelEntry)
        )

    entries = ProviderLitserveCatalogEntries(
        embedding=_pairs("embedding"),
        rerank=_pairs("rerank"),
        stt=_stt(),
        tts=_tts(),
        vad=_vad(),
    )
    _catalog_cache = (now, entries)
    return entries
