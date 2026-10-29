"""Оценки моделей компании system."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar, Self, override

from oxyde import Field as DbField

from core.ai.providers import AICapability
from core.models.platform_model import PlatformModel

EDITORIAL_PRIOR_CAP = 5.0

class LLMModelScore(PlatformModel):
    """Ручная поправка score. Глобальная таблица ``llm_model_scores`` в ``platform_shared``."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    llm_model_score_id: str = DbField(default="", db_pk=True)

    class Meta:
        is_table: bool = True
        table_name: str = "llm_model_scores"
        unique_together: list[tuple[str, str, str]] = [("provider", "model_id", "capability")]

    provider: str = DbField(db_index=True, max_length=64)
    model_id: str = DbField(db_index=True, max_length=512)
    capability: AICapability = DbField(db_index=True)
    enabled: bool = DbField(default=True, db_index=True)
    editorial_prior: float = DbField(default=0.0, ge=-5, le=5)
    note: str | None = DbField(default=None, db_type="TEXT")
    updated_by_user_id: str | None = DbField(default=None)
    created_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc), db_index=True)

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        if self.provider == "" or self.model_id == "":
            raise ValueError("provider and model_id are required")
        self.llm_model_score_id = f"{self.capability}:{self.provider}:{self.model_id}"
        self.updated_at = datetime.now(timezone.utc)

    @classmethod
    async def list_by_capability_provider_and_model_id_asc(cls) -> list[Self]:
        """Все оценки, ORDER BY capability, provider, model_id ASC. Предела нет."""
        return await cls.objects.order_by("capability", "provider", "model_id").all()

    @classmethod
    async def list_unordered_for_capability(cls, capability: AICapability | str) -> list[Self]:
        """Оценки одной capability. Порядка и предела нет."""
        return await cls.objects.filter(capability=_score_capability(capability)).all()

    @classmethod
    async def by_provider_model_id_and_capability(
        cls,
        *,
        provider: str,
        model_id: str,
        capability: AICapability | str,
    ) -> Self | None:
        """Уникальный ключ provider, model_id, capability. Нет строки — None."""
        return await cls.objects.filter(
            provider=_required_score_field(provider, "provider"),
            model_id=_required_score_field(model_id, "model_id"),
            capability=_score_capability(capability),
        ).get_or_none()

    @classmethod
    async def upsert_result_by_provider_model_id_and_capability(
        cls,
        *,
        provider: str,
        model_id: str,
        capability: AICapability | str,
        enabled: bool = True,
        editorial_prior: float = 0.0,
        note: str | None = None,
        updated_by_user_id: str | None = None,
    ) -> LLMModelScoreUpsertResult:
        """Слияние по ключу provider, model_id, capability. created — только при вставке, updated всегда True."""
        provider = _required_score_field(provider, "provider")
        model_id = _required_score_field(model_id, "model_id")
        capability_value = _score_capability(capability)
        prior = _editorial_prior(editorial_prior)
        now = datetime.now(timezone.utc)
        row = await cls.by_provider_model_id_and_capability(provider=provider, model_id=model_id, capability=capability_value)
        if row is None:
            created = cls(
                provider=provider,
                model_id=model_id,
                capability=capability_value,
                enabled=enabled,
                editorial_prior=prior,
                note=note,
                updated_by_user_id=updated_by_user_id,
                created_at=now,
                updated_at=now,
            )
            _ = await cls.objects.create(instance=created)
            return LLMModelScoreUpsertResult(row=created, created=True, updated=True)
        row.enabled = enabled
        row.editorial_prior = prior
        row.note = note
        row.updated_by_user_id = updated_by_user_id
        row.updated_at = now
        _ = await row.save()
        return LLMModelScoreUpsertResult(row=row, created=False, updated=True)

    @classmethod
    async def delete_by_provider_model_id_and_capability(
        cls,
        *,
        provider: str,
        model_id: str,
        capability: AICapability | str,
    ) -> bool:
        """Удаление по ключу provider, model_id, capability. Нет строки — False."""
        deleted = await cls.objects.filter(
            provider=_required_score_field(provider, "provider"),
            model_id=_required_score_field(model_id, "model_id"),
            capability=_score_capability(capability),
        ).delete()
        return deleted > 0

@dataclass(frozen=True)
class LLMModelScoreUpsertResult:
    row: LLMModelScore
    created: bool
    updated: bool

def _required_score_field(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if cleaned == "":
        raise ValueError(f"{field_name} cannot be empty.")
    return cleaned

def _score_capability(value: AICapability | str) -> AICapability:
    raw = value.value if isinstance(value, AICapability) else value
    cleaned = raw.strip()
    if cleaned == "":
        raise ValueError("capability cannot be empty.")
    return AICapability(cleaned)

def _editorial_prior(value: float) -> float:
    if value < -EDITORIAL_PRIOR_CAP or value > EDITORIAL_PRIOR_CAP:
        raise ValueError(
            f"editorial_prior must be in range {-EDITORIAL_PRIOR_CAP}..{EDITORIAL_PRIOR_CAP}"
        )
    return value
