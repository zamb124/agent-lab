"""Общие модели речевых провайдеров."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import ClassVar, Literal, Self, override

from oxyde import Field as DbField
from oxyde.exceptions import IntegrityError
from oxyde.queries.base import SupportsExecute
from pydantic import Field, SerializerFunctionWrapHandler, model_serializer

from core.models.base import StrictBaseModel
from core.models.company_voice_provider_secrets import (
    UNSET_SECRETS,
    SecretsPatchValue,
    is_unset_sentinel,
)
from core.models.platform_model import PlatformModel
from core.types import JsonObject, require_serializer_json_object

VoiceKind = Literal["stt", "tts", "vad"]


class VADSegment(StrictBaseModel):
    """Один сегмент с речью (в секундах относительно начала аудио)."""

    start: float = Field(ge=0.0, description="Начало сегмента (с).")
    end: float = Field(gt=0.0, description="Конец сегмента (с).")



def _voice_required_company(company_id: str) -> str:
    if company_id == "":
        raise ValueError("company_id cannot be empty.")
    return company_id


def _voice_stored_secrets(raw: dict[str, str] | None) -> dict[str, str] | None:
    if raw is None:
        return None
    normalized = {key: value for key, value in raw.items() if value != ""}
    if len(normalized) == 0:
        return None
    return normalized


def _voice_secrets_column(
    existing: CompanyVoiceProvider | None,
    secrets: SecretsPatchValue,
) -> dict[str, str] | None:
    if is_unset_sentinel(secrets):
        current = existing.secrets if existing is not None else None
        return _voice_stored_secrets(current)
    if secrets is None:
        return None
    return _voice_stored_secrets(secrets)


class CompanyVoiceProvider(PlatformModel):
    """Перекрывает ``settings.voice.<kind>`` для компании. ``secrets`` в JSON не отдаётся.

    ``__global_model__``: строку читают по ``company_id`` сессии речи, не по активной компании запроса.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    company_voice_provider_id: str = DbField(default="", db_pk=True)

    class Meta:
        is_table: bool = True
        table_name: str = "company_voice_providers"
        unique_together: list[tuple[str, str]] = [("company_id", "kind")]

    company_id: str = DbField(db_index=True)
    kind: VoiceKind = DbField(db_index=True)
    provider: str = DbField()
    model: str | None = DbField(default=None)
    voice: str | None = DbField(default=None)
    language: str | None = DbField(default=None)
    sample_rate: int | None = DbField(default=None)
    threshold: float | None = DbField(default=None)
    response_format: str | None = DbField(default=None)
    secrets: dict[str, str] | None = DbField(default=None, db_type="JSONB")
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))

    @model_serializer(mode="wrap", when_used="json")
    def _json_without_secrets(self, handler: SerializerFunctionWrapHandler) -> JsonObject:
        payload = require_serializer_json_object(handler, self, "CompanyVoiceProvider")
        if "secrets" in payload:
            del payload["secrets"]
        return payload

    @override
    async def save(
        self,
        *,
        client: SupportsExecute | None = None,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> Self:
        if self.company_voice_provider_id == "":
            if self.company_id == "" or self.provider == "":
                raise ValueError("company_id and provider are required")
            self.company_voice_provider_id = f"{self.company_id}:{self.kind}"
            self.updated_at = datetime.now(timezone.utc)
            return await type(self).objects.create(instance=self, client=client, using=using)
        return await super().save(client=client, using=using, update_fields=update_fields)

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        if self.company_id == "" or self.provider == "":
            raise ValueError("company_id and provider are required")
        self.company_voice_provider_id = f"{self.company_id}:{self.kind}"
        self.updated_at = datetime.now(timezone.utc)


    @classmethod
    async def by_kind(cls, *, company_id: str, kind: VoiceKind) -> Self | None:
        return await cls.objects.filter(
            company_id=_voice_required_company(company_id),
            kind=kind,
        ).get_or_none()

    @classmethod
    async def list_by_kind_for_company_asc(cls, *, company_id: str) -> list[Self]:
        """Все провайдеры компании, ORDER BY kind ASC. Предела нет. Пустой company_id — ValueError."""
        return await cls.objects.filter(
            company_id=_voice_required_company(company_id),
        ).order_by("kind").all()

    @classmethod
    async def upsert_by_kind(
        cls,
        *,
        company_id: str,
        kind: VoiceKind,
        provider: str,
        model: str | None = None,
        voice: str | None = None,
        language: str | None = None,
        sample_rate: int | None = None,
        threshold: float | None = None,
        response_format: str | None = None,
        secrets: SecretsPatchValue = UNSET_SECRETS,
    ) -> Self:
        company_id = _voice_required_company(company_id)
        if provider == "":
            raise ValueError("provider cannot be empty.")
        existing = await cls.by_kind(company_id=company_id, kind=kind)
        secrets_value = _voice_secrets_column(existing, secrets)
        now = datetime.now(timezone.utc)
        if existing is None:
            created = cls(
                company_id=company_id,
                kind=kind,
                provider=provider,
                model=model,
                voice=voice,
                language=language,
                sample_rate=sample_rate,
                threshold=threshold,
                response_format=response_format,
                secrets=secrets_value,
                updated_at=now,
            )
            try:
                _ = await created.save()
            except IntegrityError:
                raced = await cls.by_kind(company_id=company_id, kind=kind)
                if raced is None:
                    raise
                return await cls._assign(
                    raced,
                    provider=provider,
                    model=model,
                    voice=voice,
                    language=language,
                    sample_rate=sample_rate,
                    threshold=threshold,
                    response_format=response_format,
                    secrets=secrets_value,
                    updated_at=now,
                )
            return created
        return await cls._assign(
            existing,
            provider=provider,
            model=model,
            voice=voice,
            language=language,
            sample_rate=sample_rate,
            threshold=threshold,
            response_format=response_format,
            secrets=secrets_value,
            updated_at=now,
        )

    @classmethod
    async def delete_by_company_kind(cls, *, company_id: str, kind: VoiceKind) -> bool:
        deleted = await cls.objects.filter(
            company_id=_voice_required_company(company_id),
            kind=kind,
        ).delete()
        return deleted > 0

    @classmethod
    async def _assign(
        cls,
        row: Self,
        *,
        provider: str,
        model: str | None,
        voice: str | None,
        language: str | None,
        sample_rate: int | None,
        threshold: float | None,
        response_format: str | None,
        secrets: dict[str, str] | None,
        updated_at: datetime,
    ) -> Self:
        row.provider = provider
        row.model = model
        row.voice = voice
        row.language = language
        row.sample_rate = sample_rate
        row.threshold = threshold
        row.response_format = response_format
        row.secrets = secrets
        row.updated_at = updated_at
        _ = await row.save()
        return row

