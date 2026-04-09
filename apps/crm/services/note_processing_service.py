"""
Единый конвейер обработки заметки: analyze (AI-извлечение) + apply (создание entities/relationships).

Заметка — единственный источник данных: текст берётся из note.description + attachment_ids.
Вызывается как из HTTP (через TaskIQ), так и из воркера импорта (прямой вызов).
"""

from __future__ import annotations

from typing import Optional

from apps.crm.models.api import (
    AIAnalyzeRequest,
    AIAnalyzeResponse,
    AIAnalysisDraftApplyResult,
    NoteProcessingConfig,
    NoteProcessingResult,
)
from apps.crm.services.entity_service import EntityService
from apps.crm.services.file_text_reader import load_text_from_stored_file_id


class NoteProcessingService:
    def __init__(self, entity_service: EntityService) -> None:
        self._entity_service = entity_service

    async def resolve_note_text(
        self,
        note_id: str,
        *,
        include_attachments: bool = True,
    ) -> str:
        """Собрать текст из description + текстового содержимого вложений."""
        note = await self._entity_service.get_entity(note_id)
        if note is None:
            raise ValueError(f"Заметка не найдена: {note_id}")

        parts: list[str] = []
        if note.description:
            stripped = note.description.strip()
            if stripped:
                parts.append(stripped)

        if include_attachments and note.attachment_ids:
            for file_id in note.attachment_ids:
                text = await load_text_from_stored_file_id(file_id)
                stripped = text.strip()
                if stripped:
                    parts.append(stripped)

        combined = "\n\n---\n\n".join(parts)
        if not combined.strip():
            raise ValueError(f"Заметка {note_id} не содержит текста для анализа")
        return combined

    async def analyze(
        self,
        note_id: str,
        config: NoteProcessingConfig,
    ) -> AIAnalyzeResponse:
        """Шаг 1: AI-анализ текста заметки, сохранение черновика."""
        note = await self._entity_service.get_entity(note_id)
        if note is None:
            raise ValueError(f"Заметка не найдена: {note_id}")

        text = await self.resolve_note_text(
            note_id,
            include_attachments=config.include_attachments,
        )
        namespace = note.namespace or "default"

        req = AIAnalyzeRequest(
            text=text,
            extract_entity_types=config.extract_entity_types,
            extract_relationship_types=config.extract_relationship_types,
            mentioned_entity_ids=config.mentioned_entity_ids,
            namespace=namespace,
        )

        return await self._entity_service.analyze_text_with_ai(
            req,
            check_duplicates=config.check_duplicates,
            note_id=note_id,
        )

    async def apply(self, note_id: str) -> AIAnalysisDraftApplyResult:
        """Шаг 2: применение черновика анализа (создание entities + relationships)."""
        return await self._entity_service.apply_analysis_draft(note_id)

    async def process(
        self,
        note_id: str,
        config: NoteProcessingConfig,
    ) -> NoteProcessingResult:
        """Полный конвейер: analyze + apply."""
        await self.analyze(note_id, config)
        apply_result = await self.apply(note_id)
        return NoteProcessingResult(
            note_id=note_id,
            created_entity_ids=apply_result.created_entity_ids,
            updated_entity_ids=apply_result.updated_entity_ids,
            created_relationship_ids=apply_result.created_relationship_ids,
        )
