"""
Единый конвейер обработки заметки: analyze (AI-извлечение) + apply (создание entities/relationships).

Заметка — единственный источник данных: текст берётся из note.description + attachment_ids.
Вызывается из воркера; статусы публикуются через TaskRepository.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

from apps.crm.models.api import (
    AIAnalyzeRequest,
    AIAnalyzeResponse,
    AIAnalysisDraftApplyResult,
    NoteProcessingConfig,
    NoteProcessingResult,
)
from apps.crm.services.entity_service import EntityService
from apps.crm.services.file_text_reader import load_text_and_name_from_stored_file_id

ProgressCb = Callable[[str, int, str], Awaitable[None]]


class NoteProcessingService:
    def __init__(self, entity_service: EntityService) -> None:
        self._entity_service = entity_service

    async def resolve_note_text(
        self,
        note_id: str,
        *,
        include_attachments: bool = True,
        attachment_chars_limit: int = 40_000,
        progress_cb: Optional[ProgressCb] = None,
    ) -> str:
        """Собрать текст из description + текстового содержимого вложений.

        Если текст вложения превышает attachment_chars_limit символов,
        он суммаризируется LLM перед добавлением в общий контекст.
        Если любое вложение не содержит извлекаемого текста — бросает ValueError.
        """
        note = await self._entity_service.get_entity(note_id)
        if note is None:
            raise ValueError(f"Заметка не найдена: {note_id}")

        parts: list[str] = []
        if note.description:
            stripped = note.description.strip()
            if stripped:
                parts.append(stripped)

        if include_attachments and note.attachment_ids:
            if progress_cb:
                await progress_cb("reading_attachments", 15, "Чтение вложений")
            for i, file_id in enumerate(note.attachment_ids):
                text, filename = await load_text_and_name_from_stored_file_id(file_id)
                stripped = text.strip()
                if not stripped:
                    raise ValueError(
                        f"Вложение '{filename}' (file_id={file_id}) не содержит извлекаемого текста. "
                        "Анализ без полного содержимого всех вложений невозможен."
                    )
                if len(stripped) > attachment_chars_limit:
                    if progress_cb:
                        await progress_cb("summarizing", 35, "Суммаризация вложений")
                    stripped = await self._entity_service.call_summarize_attachment(
                        stripped, filename
                    )
                    stripped = stripped.strip()
                    if not stripped:
                        raise ValueError(
                            f"Суммаризация вложения '{filename}' (file_id={file_id}) не вернула текст."
                        )
                parts.append(f"=== Вложение {i + 1}: {filename} ===\n{stripped}")

        combined = "\n\n---\n\n".join(parts)
        if not combined.strip():
            raise ValueError(f"Заметка {note_id} не содержит текста для анализа")
        return combined

    async def analyze(
        self,
        note_id: str,
        config: NoteProcessingConfig,
        *,
        progress_cb: Optional[ProgressCb] = None,
    ) -> AIAnalyzeResponse:
        """Шаг 1: AI-анализ текста заметки, сохранение черновика."""
        note = await self._entity_service.get_entity(note_id)
        if note is None:
            raise ValueError(f"Заметка не найдена: {note_id}")

        text = await self.resolve_note_text(
            note_id,
            include_attachments=config.include_attachments,
            attachment_chars_limit=config.attachment_chars_limit_per_file,
            progress_cb=progress_cb,
        )
        if progress_cb:
            await progress_cb("preparing", 50, "Подготовка анализа")
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
            progress_cb=progress_cb,
        )

    async def apply(
        self,
        note_id: str,
        *,
        progress_cb: Optional[ProgressCb] = None,
    ) -> AIAnalysisDraftApplyResult:
        """Шаг 2: применение черновика анализа (создание entities + relationships)."""
        result = await self._entity_service.apply_analysis_draft(note_id)
        all_entity_ids = result.created_entity_ids + result.updated_entity_ids

        note_voice_id = await self._entity_service.get_note_voice_entity_id(note_id)
        sync_entity_ids = list(all_entity_ids)
        if note_voice_id and note_voice_id not in sync_entity_ids:
            sync_entity_ids.append(note_voice_id)

        if progress_cb:
            await progress_cb("linking", 94, "Связывание упоминаний")
        await self._entity_service.sync_note_mentions_from_applied_entities(
            note_id, sync_entity_ids
        )
        await self._entity_service.enrich_note_description_with_mention_tokens(note_id)
        return result

    async def process(
        self,
        note_id: str,
        config: NoteProcessingConfig,
        *,
        progress_cb: Optional[ProgressCb] = None,
    ) -> NoteProcessingResult:
        """Полный конвейер: analyze + apply."""
        await self.analyze(note_id, config, progress_cb=progress_cb)
        if progress_cb:
            await progress_cb("applying", 88, "Применение результатов")
        apply_result = await self.apply(note_id, progress_cb=progress_cb)
        return NoteProcessingResult(
            note_id=note_id,
            created_entity_ids=apply_result.created_entity_ids,
            updated_entity_ids=apply_result.updated_entity_ids,
            created_relationship_ids=apply_result.created_relationship_ids,
        )
