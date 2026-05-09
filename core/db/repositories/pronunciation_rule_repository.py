"""Репозитории для таблиц правил произношения TTS.

``PlatformPronunciationRuleRepository`` — глобальные правила (system/superadmin).
``CompanyPronunciationRuleRepository``  — per-company правила.

Оба используются только из ``core.clients.voice_resolver`` и REST-хендлеров
``apps/frontend/api/``. Прямой импорт в ``apps/**`` запрещён в пользу
DI ``ContainerDep``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select

from core.db.database import get_session_factory
from core.db.models.platform import CompanyPronunciationRule, PlatformPronunciationRule


class PlatformPronunciationRuleRepository:
    """CRUD для ``platform_pronunciation_rules``."""

    def __init__(self, db_url: str) -> None:
        if db_url == "":
            raise ValueError("PlatformPronunciationRuleRepository: db_url не может быть пустым.")
        self._db_url = db_url

    async def list_enabled(self) -> list[PlatformPronunciationRule]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(PlatformPronunciationRule)
                .where(PlatformPronunciationRule.enabled.is_(True))
                .order_by(PlatformPronunciationRule.created_at)
            )
            return list(result.scalars().all())

    async def list_all(self) -> list[PlatformPronunciationRule]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(PlatformPronunciationRule).order_by(
                    PlatformPronunciationRule.created_at
                )
            )
            return list(result.scalars().all())

    async def get(self, rule_id: str) -> Optional[PlatformPronunciationRule]:
        if rule_id == "":
            raise ValueError("rule_id не может быть пустым.")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(PlatformPronunciationRule).where(
                    PlatformPronunciationRule.id == rule_id
                )
            )
            return result.scalar_one_or_none()

    async def create(
        self,
        *,
        kind: str,
        pattern: str,
        replacement: str,
        language: Optional[str] = None,
        case_sensitive: bool = False,
        word_boundary: bool = True,
        providers: Optional[list[str]] = None,
        voices: Optional[list[str]] = None,
        enabled: bool = True,
        note: Optional[str] = None,
    ) -> PlatformPronunciationRule:
        if pattern == "":
            raise ValueError("pattern не может быть пустым.")
        now = datetime.now(timezone.utc)
        rule = PlatformPronunciationRule(
            id=str(uuid.uuid4()),
            kind=kind,
            pattern=pattern,
            replacement=replacement,
            language=language,
            case_sensitive=case_sensitive,
            word_boundary=word_boundary,
            providers=providers,
            voices=voices,
            enabled=enabled,
            note=note,
            created_at=now,
            updated_at=now,
        )
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            session.add(rule)
            await session.commit()
            await session.refresh(rule)
        return rule

    async def update(
        self,
        rule_id: str,
        *,
        kind: Optional[str] = None,
        pattern: Optional[str] = None,
        replacement: Optional[str] = None,
        language: Optional[str] = None,
        case_sensitive: Optional[bool] = None,
        word_boundary: Optional[bool] = None,
        providers: Optional[list[str]] = None,
        voices: Optional[list[str]] = None,
        enabled: Optional[bool] = None,
        note: Optional[str] = None,
    ) -> Optional[PlatformPronunciationRule]:
        if rule_id == "":
            raise ValueError("rule_id не может быть пустым.")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(PlatformPronunciationRule).where(
                    PlatformPronunciationRule.id == rule_id
                )
            )
            rule = result.scalar_one_or_none()
            if rule is None:
                return None
            if kind is not None:
                rule.kind = kind
            if pattern is not None:
                rule.pattern = pattern
            if replacement is not None:
                rule.replacement = replacement
            if language is not None:
                rule.language = language
            if case_sensitive is not None:
                rule.case_sensitive = case_sensitive
            if word_boundary is not None:
                rule.word_boundary = word_boundary
            if providers is not None:
                rule.providers = providers
            if voices is not None:
                rule.voices = voices
            if enabled is not None:
                rule.enabled = enabled
            if note is not None:
                rule.note = note
            rule.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(rule)
        return rule

    async def delete(self, rule_id: str) -> bool:
        if rule_id == "":
            raise ValueError("rule_id не может быть пустым.")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                delete(PlatformPronunciationRule).where(
                    PlatformPronunciationRule.id == rule_id
                )
            )
            await session.commit()
            return result.rowcount > 0


class CompanyPronunciationRuleRepository:
    """CRUD для ``company_pronunciation_rules``."""

    def __init__(self, db_url: str) -> None:
        if db_url == "":
            raise ValueError("CompanyPronunciationRuleRepository: db_url не может быть пустым.")
        self._db_url = db_url

    async def count_by_company(self, *, company_id: str) -> int:
        if company_id == "":
            raise ValueError("company_id не может быть пустым.")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            from sqlalchemy import func
            result = await session.execute(
                select(func.count()).where(
                    CompanyPronunciationRule.company_id == company_id
                )
            )
            return result.scalar_one()

    async def list_enabled(self, *, company_id: str) -> list[CompanyPronunciationRule]:
        if company_id == "":
            raise ValueError("company_id не может быть пустым.")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(CompanyPronunciationRule)
                .where(
                    CompanyPronunciationRule.company_id == company_id,
                    CompanyPronunciationRule.enabled.is_(True),
                )
                .order_by(CompanyPronunciationRule.created_at)
            )
            return list(result.scalars().all())

    async def list_all(self, *, company_id: str) -> list[CompanyPronunciationRule]:
        if company_id == "":
            raise ValueError("company_id не может быть пустым.")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(CompanyPronunciationRule)
                .where(CompanyPronunciationRule.company_id == company_id)
                .order_by(CompanyPronunciationRule.created_at)
            )
            return list(result.scalars().all())

    async def get(self, *, company_id: str, rule_id: str) -> Optional[CompanyPronunciationRule]:
        if company_id == "":
            raise ValueError("company_id не может быть пустым.")
        if rule_id == "":
            raise ValueError("rule_id не может быть пустым.")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(CompanyPronunciationRule).where(
                    CompanyPronunciationRule.company_id == company_id,
                    CompanyPronunciationRule.id == rule_id,
                )
            )
            return result.scalar_one_or_none()

    async def create(
        self,
        *,
        company_id: str,
        kind: str,
        pattern: str,
        replacement: str,
        language: Optional[str] = None,
        case_sensitive: bool = False,
        word_boundary: bool = True,
        providers: Optional[list[str]] = None,
        voices: Optional[list[str]] = None,
        enabled: bool = True,
        note: Optional[str] = None,
        max_rules: int = 1000,
    ) -> CompanyPronunciationRule:
        if company_id == "":
            raise ValueError("company_id не может быть пустым.")
        if pattern == "":
            raise ValueError("pattern не может быть пустым.")
        current_count = await self.count_by_company(company_id=company_id)
        if current_count >= max_rules:
            raise ValueError(
                f"Достигнут лимит правил для компании {company_id!r}: "
                f"{current_count}/{max_rules}. Удалите часть правил перед добавлением."
            )
        now = datetime.now(timezone.utc)
        rule = CompanyPronunciationRule(
            id=str(uuid.uuid4()),
            company_id=company_id,
            kind=kind,
            pattern=pattern,
            replacement=replacement,
            language=language,
            case_sensitive=case_sensitive,
            word_boundary=word_boundary,
            providers=providers,
            voices=voices,
            enabled=enabled,
            note=note,
            created_at=now,
            updated_at=now,
        )
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            session.add(rule)
            await session.commit()
            await session.refresh(rule)
        return rule

    async def update(
        self,
        *,
        company_id: str,
        rule_id: str,
        kind: Optional[str] = None,
        pattern: Optional[str] = None,
        replacement: Optional[str] = None,
        language: Optional[str] = None,
        case_sensitive: Optional[bool] = None,
        word_boundary: Optional[bool] = None,
        providers: Optional[list[str]] = None,
        voices: Optional[list[str]] = None,
        enabled: Optional[bool] = None,
        note: Optional[str] = None,
    ) -> Optional[CompanyPronunciationRule]:
        if company_id == "":
            raise ValueError("company_id не может быть пустым.")
        if rule_id == "":
            raise ValueError("rule_id не может быть пустым.")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(CompanyPronunciationRule).where(
                    CompanyPronunciationRule.company_id == company_id,
                    CompanyPronunciationRule.id == rule_id,
                )
            )
            rule = result.scalar_one_or_none()
            if rule is None:
                return None
            if kind is not None:
                rule.kind = kind
            if pattern is not None:
                rule.pattern = pattern
            if replacement is not None:
                rule.replacement = replacement
            if language is not None:
                rule.language = language
            if case_sensitive is not None:
                rule.case_sensitive = case_sensitive
            if word_boundary is not None:
                rule.word_boundary = word_boundary
            if providers is not None:
                rule.providers = providers
            if voices is not None:
                rule.voices = voices
            if enabled is not None:
                rule.enabled = enabled
            if note is not None:
                rule.note = note
            rule.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(rule)
        return rule

    async def delete(self, *, company_id: str, rule_id: str) -> bool:
        if company_id == "":
            raise ValueError("company_id не может быть пустым.")
        if rule_id == "":
            raise ValueError("rule_id не может быть пустым.")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                delete(CompanyPronunciationRule).where(
                    CompanyPronunciationRule.company_id == company_id,
                    CompanyPronunciationRule.id == rule_id,
                )
            )
            await session.commit()
            return result.rowcount > 0


__all__ = [
    "CompanyPronunciationRuleRepository",
    "PlatformPronunciationRuleRepository",
]
