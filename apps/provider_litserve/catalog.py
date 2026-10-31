"""Boot-time каталог моделей provider_litserve и seed желаемого состояния.

``ModelCatalog`` — иммутабельный снимок ``ready``-строк таблицы
``provider_litserve_models`` на момент старта процесса. LitServe spawn-воркеры
получают его через pickle вместе с LitAPI: модели, ставшие ``ready`` уже после
старта пода, обслуживаются после рестарта пода.

``sync_seed_entries`` — идемпотентный seed желаемого состояния из
``provider_litserve.infra`` конфига в таблицу (запускается до спауна воркеров).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, TypeAlias, overload

from core.config.models import (
    ProviderLitserveInfraConfig,
    ProviderLitserveSTTModelEntry,
    ProviderLitserveTTSModelEntry,
    ProviderLitserveVADModelEntry,
)
from core.logging import get_logger
from core.models.provider_litserve_model import (
    LITSERVE_MODEL_KINDS,
    LitserveCatalogEntry,
    LitserveModelKind,
    ProviderLitserveModel,
    ProviderLitserveModelPair,
)

logger = get_logger(__name__)

SeedEntry: TypeAlias = tuple[LitserveModelKind, LitserveCatalogEntry]


def _api_key_norm(s: str) -> str:
    return s.strip().lower()


def _build_pairs(
    *,
    hf_model_id: str,
    openai_model_id: str,
    extra_model_ids: Sequence[str],
    dimension: int | None,
    context_length: int | None,
) -> list[ProviderLitserveModelPair]:
    """Пары api-id → HF id без дублей: alias на тот же hf не дублирует hf→hf.

    ``dimension``/``context_length`` — свойства primary-весов, поэтому ставятся
    только на пары, адресующие ``hf_model_id``; extra-id — чужие модели.
    """
    out: dict[str, str] = {}
    hf = hf_model_id.strip()
    api = openai_model_id.strip()
    if api:
        out[api] = hf
    if hf and not any(v.strip().lower() == hf.lower() for v in out.values()):
        out[hf] = hf
    for model_id in extra_model_ids:
        n = model_id.strip()
        if not n:
            continue
        if any(_api_key_norm(n) == _api_key_norm(k) for k in out):
            continue
        out[n] = n
    return [
        ProviderLitserveModelPair(
            api_model_id=api_id,
            hf_model_id=hf_id,
            dimension=dimension if hf_id == hf else None,
            context_length=context_length if hf_id == hf else None,
        )
        for api_id, hf_id in out.items()
    ]


def build_embedding_seed_entries(cfg: ProviderLitserveInfraConfig) -> list[ProviderLitserveModelPair]:
    return _build_pairs(
        hf_model_id=cfg.embedding_model_id,
        openai_model_id=cfg.embedding_openai_model_id,
        extra_model_ids=cfg.embedding_model_ids,
        dimension=cfg.embedding_dimension,
        context_length=cfg.max_length,
    )


def build_rerank_seed_entries(cfg: ProviderLitserveInfraConfig) -> list[ProviderLitserveModelPair]:
    return _build_pairs(
        hf_model_id=cfg.rerank_model_id,
        openai_model_id=cfg.rerank_openai_model_id,
        extra_model_ids=cfg.rerank_model_ids,
        dimension=None,
        context_length=cfg.max_length,
    )


def _validate_audio_entries(
    *,
    entries: Sequence[LitserveCatalogEntry],
    kind_label: str,
) -> None:
    """Дубликаты api-id и пустые id в списке (Zero-Guess — ValueError)."""
    seen: set[str] = set()
    for entry in entries:
        api_id = entry.api_model_id.strip()
        hf_id = entry.hf_model_id.strip()
        if not api_id:
            raise ValueError(
                f"provider_litserve {kind_label}_models: empty api_model_id in record"
            )
        if not hf_id:
            raise ValueError(
                f"provider_litserve {kind_label}_models: empty hf_model_id for api_model_id={api_id!r}"
            )
        api_lower = api_id.lower()
        if api_lower in seen:
            raise ValueError(
                f"provider_litserve {kind_label}_models: duplicate api_model_id={api_id!r}"
            )
        seen.add(api_lower)



def build_stt_seed_entries(cfg: ProviderLitserveInfraConfig) -> list[ProviderLitserveSTTModelEntry]:
    entries = list(cfg.stt_models)
    _validate_audio_entries(
        entries=entries,
        kind_label="stt",
    )
    return entries


def build_tts_seed_entries(cfg: ProviderLitserveInfraConfig) -> list[ProviderLitserveTTSModelEntry]:
    entries = list(cfg.tts_models)
    _validate_audio_entries(
        entries=entries,
        kind_label="tts",
    )
    return entries


def build_vad_seed_entries(cfg: ProviderLitserveInfraConfig) -> list[ProviderLitserveVADModelEntry]:
    entries = list(cfg.vad_models)
    _validate_audio_entries(
        entries=entries,
        kind_label="vad",
    )
    return entries


def build_seed_entries(cfg: ProviderLitserveInfraConfig) -> list[SeedEntry]:
    """Желаемое состояние каталога из конфига (kind, запись)."""
    seeds: list[SeedEntry] = [
        ("embedding", entry) for entry in build_embedding_seed_entries(cfg)
    ]
    seeds.extend(("rerank", entry) for entry in build_rerank_seed_entries(cfg))
    seeds.extend(("stt", entry) for entry in build_stt_seed_entries(cfg))
    seeds.extend(("tts", entry) for entry in build_tts_seed_entries(cfg))
    seeds.extend(("vad", entry) for entry in build_vad_seed_entries(cfg))
    return seeds


async def sync_seed_entries(cfg: ProviderLitserveInfraConfig) -> int:
    """Идемпотентно записать conf-seed в таблицу. Tombstone ``deleted`` не трогает."""
    written = 0
    for kind, entry in build_seed_entries(cfg):
        row = await ProviderLitserveModel.upsert_seed(kind=kind, entry=entry)
        if row is not None:
            written += 1
    return written


class ModelCatalog:
    """Снимок моделей по kind для ``/v1/models`` и резолва внутри воркеров."""

    def __init__(
        self,
        entries: Mapping[LitserveModelKind, Sequence[LitserveCatalogEntry]],
    ) -> None:
        self._entries: dict[LitserveModelKind, tuple[LitserveCatalogEntry, ...]] = {
            kind: tuple(entries.get(kind, ())) for kind in LITSERVE_MODEL_KINDS
        }

    @classmethod
    def from_seed(cls, cfg: ProviderLitserveInfraConfig) -> ModelCatalog:
        """Каталог только из conf-seed (тесты, ASGI-приложение без БД)."""
        grouped: dict[LitserveModelKind, list[LitserveCatalogEntry]] = {
            kind: [] for kind in LITSERVE_MODEL_KINDS
        }
        for kind, entry in build_seed_entries(cfg):
            grouped[kind].append(entry)
        return cls(grouped)

    @classmethod
    async def load(cls, *, enabled_kinds: frozenset[str] | None = None) -> ModelCatalog:
        """Каталог из ready-строк таблицы; ``enabled_kinds`` — воркеры пода."""
        grouped: dict[LitserveModelKind, list[LitserveCatalogEntry]] = {
            kind: [] for kind in LITSERVE_MODEL_KINDS
        }
        for row in await ProviderLitserveModel.list_ready_by_created_at_asc():
            if enabled_kinds is not None and row.kind not in enabled_kinds:
                continue
            grouped[row.kind].append(row.to_entry())
        return cls(grouped)

    def entries(self, kind: LitserveModelKind) -> tuple[LitserveCatalogEntry, ...]:
        return self._entries[kind]

    def api_model_ids(self, kind: LitserveModelKind) -> list[str]:
        return sorted(entry.api_model_id for entry in self._entries[kind])

    def default_api_model_id(self, kind: LitserveModelKind) -> str:
        """Дефолт kind — самая старая ready-запись (порядок seed/created_at)."""
        entries = self._entries[kind]
        return entries[0].api_model_id if entries else ""

    def allowed_ids(self, kind: LitserveModelKind) -> frozenset[str]:
        return frozenset(entry.api_model_id for entry in self._entries[kind])

    def find_entry(
        self, kind: LitserveModelKind, api_model_id: str
    ) -> LitserveCatalogEntry | None:
        needle = api_model_id.strip().lower()
        for entry in self._entries[kind]:
            if entry.api_model_id.lower() == needle:
                return entry
        return None

    @overload
    def find_typed(
        self, kind: Literal["stt"], api_model_id: str
    ) -> ProviderLitserveSTTModelEntry | None: ...

    @overload
    def find_typed(
        self, kind: Literal["tts"], api_model_id: str
    ) -> ProviderLitserveTTSModelEntry | None: ...

    @overload
    def find_typed(
        self, kind: Literal["vad"], api_model_id: str
    ) -> ProviderLitserveVADModelEntry | None: ...

    def find_typed(
        self, kind: LitserveModelKind, api_model_id: str
    ) -> LitserveCatalogEntry | None:
        return self.find_entry(kind, api_model_id)

    def hf_model_id(self, kind: LitserveModelKind, api_model_id: str) -> str | None:
        entry = self.find_entry(kind, api_model_id)
        if entry is None:
            return None
        return entry.hf_model_id
