"""
Тесты пайплайна обработки текстового содержимого вложений в AI-анализе заметки.

Проверяется:
1. resolve_note_text — сборка текста из description + вложений.
2. Малое вложение: текст включается без вызова summarize_attachment.
3. Большое вложение: сначала суммаризация LLM, потом analyze.
4. Параметр attachment_chars_limit_per_file управляет порогом суммаризации.
5. include_attachments=False полностью пропускает файлы.

Ключевой механизм верификации E2E-тестов:
mock_llm_redis раздаёт ответы строго по порядку. Если код вызывает лишний
LLM (или пропускает нужный), следующий вызов получает «чужой» ответ →
неверный JSON → тест падает. Мок-очередь кодирует ожидаемую
последовательность вызовов без явного шпионажа.
"""

from __future__ import annotations

import asyncio
import json
import time as _time
from collections.abc import Awaitable, Callable
from datetime import date
from typing import cast

import pytest
from httpx import AsyncClient, Response

from apps.crm.config import get_crm_settings
from tests.crm.e2e._json_helpers import json_object, object_dict, object_list, object_str
from tests.crm.e2e.attachment_upload_helpers import upload_and_attach_crm_file

MockLlmRedisFactory = Callable[[list[object]], Awaitable[None]]


@pytest.fixture(autouse=True)
def disable_background_markdown_format(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_crm_settings()
    monkeypatch.setattr(settings, "note_attachment_markdown_format_enabled", False)


class _DraftResponse:
    status_code: int
    _draft: dict[str, object]

    def __init__(self, status_code: int, draft: dict[str, object]) -> None:
        self.status_code = status_code
        self._draft = draft

    def json(self) -> dict[str, object]:
        return self._draft


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


async def _analyze_note_task(
    crm_client: AsyncClient,
    headers: dict[str, str],
    note_id: str,
    *,
    fail_on_failed: bool = True,
    **kwargs: object,
) -> tuple[dict[str, object], _DraftResponse]:
    """Запускает анализ и ждёт завершения. Возвращает (task_row, note_draft)."""
    body: dict[str, object] = {"note_id": note_id}
    body.update(kwargs)
    start = await crm_client.post("/crm/api/v1/tasks/note-analyze", json=body, headers=headers)
    assert start.status_code == 202, start.text
    start_payload = _http_json(start)
    task_id = object_str(start_payload.get("task_id"), field="task_id")
    deadline = _time.monotonic() + 90.0
    last: dict[str, object] = {}
    while _time.monotonic() < deadline:
        tr = await crm_client.get(f"/crm/api/v1/tasks/{task_id}", headers=headers)
        last = _http_json(tr)
        status_raw = last.get("status")
        if status_raw in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.4)
    if fail_on_failed:
        assert last.get("status") == "completed", f"task failed: {last.get('error_message')}"
    nr = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=headers)
    note_payload = _http_json(nr)
    attributes_raw = note_payload.get("attributes")
    if isinstance(attributes_raw, dict):
        attributes = object_dict(cast(object, attributes_raw), field="attributes")
    else:
        attributes = {}
    draft_raw = attributes.get("ai_analysis_draft")
    if isinstance(draft_raw, dict):
        draft = object_dict(cast(object, draft_raw), field="ai_analysis_draft")
    else:
        draft = {}
    return last, _DraftResponse(nr.status_code, draft)


def _draft_entity_count(draft_response: _DraftResponse) -> int:
    return len(object_list(draft_response.json().get("entities")))


_ANALYZE_META: dict[str, object] = {"dates_mentioned": [], "places_mentioned": [], "key_topics": []}


def _isolated_note_date(unique_id: str) -> str:
    day_offset = int(unique_id[:8], 16) % 20_000
    return date.fromordinal(date(2090, 1, 1).toordinal() + day_offset).isoformat()


def _analyze_llm_response(*, note_name: str, person_name: str) -> str:
    return json.dumps(
        {
            "note": {
                "entity_type": "note",
                "name": note_name,
                "description": "Итог анализа заметки и вложений для теста.",
                "attributes": {},
                "confidence": 0.85,
            },
            "entities": [
                {
                    "entity_type": "task",
                    "name": person_name,
                    "description": "Менеджер проекта по согласованию.",
                    "attributes": {"role": "менеджер"},
                    "confidence": 0.88,
                },
            ],
            "relationships": [
                {
                    "source_type": "note",
                    "source_name": note_name,
                    "target_type": "task",
                    "target_name": person_name,
                    "relationship_type": "mentions",
                    "weight": 1.0,
                    "confidence": 0.9,
                }
            ],
            "metadata": _ANALYZE_META,
            "attachment_summaries": [],
        }
    )


@pytest.mark.timeout(30)
class TestResolveNoteText:
    """Прямые тесты NoteProcessingService.resolve_note_text без LLM.

    Используем crm_worker_di: NoteProcessingService живёт в процессе crm_worker.
    Никакого real_taskiq не нужно — LLM не вызывается при маленьких файлах
    и при отключённой суммаризации.

    Несколько upload + чтение файлов из S3 часто превышают глобальные 5s
    на теле теста — отдельный лимит только для этого класса.
    """

    @pytest.mark.asyncio
    async def test_description_without_attachments(
        self,
        crm_client: AsyncClient,
        crm_worker_di,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Заметка без вложений: resolve_note_text возвращает только description."""
        description = f"Текст заметки {unique_id} без файлов."
        note_resp = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "entity_type": "note",
                "name": f"Тест описания {unique_id}",
                "description": description,
                "namespace": "default",
                "note_date": _isolated_note_date(unique_id),
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        text = await crm_worker_di.note_processing_service.resolve_note_text(
            note_id,
            include_attachments=True,
            attachment_chars_limit=40_000,
        )

        assert description in text

    @pytest.mark.asyncio
    async def test_small_attachment_included_verbatim(
        self,
        crm_client: AsyncClient,
        crm_worker_di,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Малое вложение (ниже лимита): полный текст файла попадает в результат без суммаризации."""
        description = f"Описание встречи {unique_id}."
        note_name = f"Малый файл {unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "entity_type": "note",
                "name": note_name,
                "description": description,
                "namespace": "default",
                "note_date": _isolated_note_date(unique_id),
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        file_text = f"Протокол совещания {unique_id}. Присутствовали: Иван Иванов, Петр Петров."
        upload = await upload_and_attach_crm_file(
            crm_client,
            auth_headers_system,
            entity_id=note_id,
            entity_type="note",
            entity_title=note_name,
            filename="protocol.txt",
            content=file_text.encode(),
            content_type="text/plain",
        )
        assert upload.status_code == 200, upload.text

        # attachment_chars_limit=1_000_000 → суммаризация не вызывается никогда
        text = await crm_worker_di.note_processing_service.resolve_note_text(
            note_id,
            include_attachments=True,
            attachment_chars_limit=1_000_000,
        )

        assert description in text
        assert "Иван Иванов" in text
        assert "Петр Петров" in text

    @pytest.mark.asyncio
    async def test_multiple_small_attachments_all_included(
        self,
        crm_client: AsyncClient,
        crm_worker_di,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Несколько малых вложений: тексты всех файлов присутствуют в результате."""
        note_name = f"Несколько файлов {unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "entity_type": "note",
                "name": note_name,
                "description": f"Основная заметка {unique_id}.",
                "namespace": "default",
                "note_date": _isolated_note_date(unique_id),
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        signatures = [f"МАРКЕР_{i}_{unique_id}" for i in range(3)]
        for i, sig in enumerate(signatures):
            upload = await upload_and_attach_crm_file(
                crm_client,
                auth_headers_system,
                entity_id=note_id,
                entity_type="note",
                entity_title=note_name,
                filename=f"doc{i}.txt",
                content=f"Содержимое {sig}.".encode(),
                content_type="text/plain",
            )
            assert upload.status_code == 200, upload.text

        text = await crm_worker_di.note_processing_service.resolve_note_text(
            note_id,
            include_attachments=True,
            attachment_chars_limit=1_000_000,
        )

        for sig in signatures:
            assert sig in text, f"Маркер '{sig}' не найден в собранном тексте"

    @pytest.mark.asyncio
    async def test_include_attachments_false_skips_files(
        self,
        crm_client: AsyncClient,
        crm_worker_di,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """include_attachments=False: файл не читается, в результате только description."""
        file_marker = f"МАРКЕР_ФАЙЛА_{unique_id}"
        description = f"Только описание {unique_id}."
        note_name = f"Флаг attachments {unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "entity_type": "note",
                "name": note_name,
                "description": description,
                "namespace": "default",
                "note_date": _isolated_note_date(unique_id),
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        upload = await upload_and_attach_crm_file(
            crm_client,
            auth_headers_system,
            entity_id=note_id,
            entity_type="note",
            entity_title=note_name,
            filename="marker.txt",
            content=f"Содержимое {file_marker}.".encode(),
            content_type="text/plain",
        )
        assert upload.status_code == 200, upload.text

        text = await crm_worker_di.note_processing_service.resolve_note_text(
            note_id,
            include_attachments=False,
            attachment_chars_limit=1_000_000,
        )

        assert description in text
        assert file_marker not in text


@pytest.mark.real_taskiq
class TestAnalyzeWithAttachments:
    """E2E тесты POST /analyze с вложениями.

    Инфраструктура: реальный TaskIQ + MockLLM в Redis. Flows, RAG, CRM — реальные.
    """

    @pytest.mark.asyncio
    async def test_small_attachment_single_llm_call(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Малое вложение (< дефолтного лимита 40k): один LLM вызов — только analyze.

        Если бы summarize_attachment вызвался, он «съел» бы единственный
        мок-ответ, analyze получил бы {"summary": ...} вместо CRM-JSON → ValueError.
        """
        note_name = f"Малый файл E2E {unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "entity_type": "note",
                "name": note_name,
                "description": f"Короткая заметка {unique_id}.",
                "namespace": "default",
                "note_date": _isolated_note_date(unique_id),
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        small_content = f"Встреча с Иваном {unique_id}. Обсудили проект."
        upload = await upload_and_attach_crm_file(
            crm_client,
            auth_headers_system,
            entity_id=note_id,
            entity_type="note",
            entity_title=note_name,
            filename="small.txt",
            content=small_content.encode(),
            content_type="text/plain",
        )
        assert upload.status_code == 200, upload.text

        await mock_llm_redis([
            {"type": "text", "content": _analyze_llm_response(note_name=note_name, person_name=f"Менеджер {unique_id}")},
        ])

        last, resp = await _analyze_note_task(
            crm_client, auth_headers_system, note_id, check_duplicates=False
        )
        assert _draft_entity_count(resp) >= 1, f"task={last} draft={resp.json()}"

    @pytest.mark.asyncio
    async def test_large_attachment_summarized_then_analyzed(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Большое вложение (> 40k символов): два LLM вызова — summarize, затем analyze.

        Порядок мок-ответов строго кодирует ожидаемую последовательность.
        Если порядок вызовов окажется другим, ни один ответ не пройдёт валидацию.
        """
        note_name = f"Большой файл E2E {unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "entity_type": "note",
                "name": note_name,
                "description": f"Заметка с большим файлом {unique_id}.",
                "namespace": "default",
                "note_date": _isolated_note_date(unique_id),
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        # 42 000 символов — превышает дефолтный порог 40 000
        phrase = f"Иван Иванов из компании Рога и Копыта обсуждал проект {unique_id}. "
        large_content = (phrase * (42_000 // len(phrase) + 1))[:42_000]
        upload = await upload_and_attach_crm_file(
            crm_client,
            auth_headers_system,
            entity_id=note_id,
            entity_type="note",
            entity_title=note_name,
            filename="large_report.txt",
            content=large_content.encode(),
            content_type="text/plain",
        )
        assert upload.status_code == 200, upload.text

        summary_text = f"Менеджер {unique_id} провёл встречу по проекту."
        # 42k символов → несколько фрагментов summarize_attachment (чанк ~18k).
        summarize_item = {"type": "text", "content": json.dumps({"summary": summary_text})}
        await mock_llm_redis(
            [
                summarize_item,
                summarize_item,
                summarize_item,
                {
                    "type": "text",
                    "content": _analyze_llm_response(
                        note_name=note_name, person_name=f"Менеджер {unique_id}"
                    ),
                },
            ]
        )

        last, resp = await _analyze_note_task(
            crm_client, auth_headers_system, note_id, check_duplicates=False
        )
        assert _draft_entity_count(resp) >= 1, f"task={last} draft={resp.json()}"

    @pytest.mark.asyncio
    async def test_attachment_chars_limit_per_file_configurable(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """attachment_chars_limit_per_file=5000 в теле запроса: файл 6k символов суммаризируется.

        Доказывает, что параметр из NoteProcessingConfig доходит до resolve_note_text.
        Дефолт — 40k, поэтому с дефолтом этот файл не суммаризировался бы.
        """
        note_name = f"Настраиваемый лимит {unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "entity_type": "note",
                "name": note_name,
                "description": f"Тест кастомного лимита {unique_id}.",
                "namespace": "default",
                "note_date": _isolated_note_date(unique_id),
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        # 6 000 символов — больше лимита 5 000, но меньше дефолта 40 000
        phrase = f"Протокол совещания {unique_id}. Присутствовал Алексей Смирнов из ООО Ромашка. "
        medium_content = (phrase * (6_000 // len(phrase) + 1))[:6_000]
        upload = await upload_and_attach_crm_file(
            crm_client,
            auth_headers_system,
            entity_id=note_id,
            entity_type="note",
            entity_title=note_name,
            filename="medium.txt",
            content=medium_content.encode(),
            content_type="text/plain",
        )
        assert upload.status_code == 200, upload.text

        await mock_llm_redis([
            # 1-й вызов: summarize_attachment (6000 > 5000 → суммаризация)
            {"type": "text", "content": json.dumps({"summary": f"Краткий протокол {unique_id}."})},
            # 2-й вызов: analyze
            {"type": "text", "content": _analyze_llm_response(note_name=note_name, person_name=f"Менеджер {unique_id}")},
        ])

        last, resp = await _analyze_note_task(
            crm_client,
            auth_headers_system,
            note_id,
            attachment_chars_limit_per_file=5_000,
            check_duplicates=False,
        )
        assert _draft_entity_count(resp) >= 1, f"task={last} draft={resp.json()}"

    @pytest.mark.asyncio
    async def test_include_attachments_false_single_llm_call(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """include_attachments=False: большой файл игнорируется — один LLM вызов (analyze).

        Если файл был бы прочитан и суммаризирован, мок-очередь опустела бы раньше срока.
        """
        note_name = f"Без вложений в анализе {unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "entity_type": "note",
                "name": note_name,
                "description": f"Анализируем только описание {unique_id}.",
                "namespace": "default",
                "note_date": _isolated_note_date(unique_id),
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        phrase = f"Данные из файла {unique_id}. "
        large_content = (phrase * (50_000 // len(phrase) + 1))[:50_000]
        upload = await upload_and_attach_crm_file(
            crm_client,
            auth_headers_system,
            entity_id=note_id,
            entity_type="note",
            entity_title=note_name,
            filename="ignored.txt",
            content=large_content.encode(),
            content_type="text/plain",
        )
        assert upload.status_code == 200, upload.text

        await mock_llm_redis([
            {"type": "text", "content": _analyze_llm_response(note_name=note_name, person_name=f"Менеджер {unique_id}")},
        ])

        last, resp = await _analyze_note_task(
            crm_client,
            auth_headers_system,
            note_id,
            include_attachments=False,
            check_duplicates=False,
        )
        assert _draft_entity_count(resp) >= 1, f"task={last} draft={resp.json()}"


class TestAttachmentGuarantee:
    """Жёсткая гарантия: вложение без текста → анализ не запускается."""

    @pytest.mark.asyncio
    async def test_empty_attachment_raises_in_resolve_note_text(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Пустой файл отклоняется на chunked upload."""
        note_name = f"Пустой файл {unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "entity_type": "note",
                "name": note_name,
                "description": f"Описание заметки {unique_id}.",
                "namespace": "default",
                "note_date": _isolated_note_date(unique_id),
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        with pytest.raises(ValueError, match="empty content"):
            _ = await upload_and_attach_crm_file(
                crm_client,
                auth_headers_system,
                entity_id=note_id,
                entity_type="note",
                entity_title=note_name,
                filename="empty.txt",
                content=b"",
                content_type="text/plain",
            )

    @pytest.mark.asyncio
    async def test_whitespace_only_attachment_raises(
        self,
        crm_client: AsyncClient,
        crm_worker_di,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Файл только из пробелов → тоже не допускается в анализ."""
        note_name = f"Пробельный файл {unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "entity_type": "note",
                "name": note_name,
                "description": f"Описание {unique_id}.",
                "namespace": "default",
                "note_date": _isolated_note_date(unique_id),
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        upload = await upload_and_attach_crm_file(
            crm_client,
            auth_headers_system,
            entity_id=note_id,
            entity_type="note",
            entity_title=note_name,
            filename="spaces.txt",
            content=b"   \n\t\n   ",
            content_type="text/plain",
        )
        assert upload.status_code == 200, upload.text

        with pytest.raises(ValueError, match="has no extractable text"):
            _ = await crm_worker_di.note_processing_service.resolve_note_text(
                note_id,
                include_attachments=True,
                attachment_chars_limit=1_000_000,
            )

    @pytest.mark.asyncio
    async def test_valid_file_passes_resolve_note_text(
        self,
        crm_client: AsyncClient,
        crm_worker_di,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Непустой файл проходит resolve_note_text; пустой отклоняется на chunked upload."""
        note_name = f"Смешанные файлы {unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "entity_type": "note",
                "name": note_name,
                "description": f"Описание {unique_id}.",
                "namespace": "default",
                "note_date": _isolated_note_date(unique_id),
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        good_content = f"Контент с информацией {unique_id}.".encode()
        upload_good = await upload_and_attach_crm_file(
            crm_client,
            auth_headers_system,
            entity_id=note_id,
            entity_type="note",
            entity_title=note_name,
            filename="good.txt",
            content=good_content,
            content_type="text/plain",
        )
        assert upload_good.status_code == 200, upload_good.text

        with pytest.raises(ValueError, match="empty content"):
            _ = await upload_and_attach_crm_file(
                crm_client,
                auth_headers_system,
                entity_id=note_id,
                entity_type="note",
                entity_title=note_name,
                filename="empty.txt",
                content=b"",
                content_type="text/plain",
            )

        text = await crm_worker_di.note_processing_service.resolve_note_text(
            note_id,
            include_attachments=True,
            attachment_chars_limit=1_000_000,
        )
        assert good_content.decode() in text


@pytest.mark.real_taskiq
class TestAnalyzeBlockedByEmptyAttachment:
    """E2E: пустое вложение → POST /analyze возвращает 422 без LLM-вызова."""

    @pytest.mark.asyncio
    async def test_empty_attachment_blocks_analyze_http(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Пустой txt → chunked upload отклоняет до attach."""

        note_name = f"HTTP пустой файл {unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "entity_type": "note",
                "name": note_name,
                "description": f"Описание {unique_id}.",
                "namespace": "default",
                "note_date": _isolated_note_date(unique_id),
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        with pytest.raises(ValueError, match="empty content"):
            _ = await upload_and_attach_crm_file(
                crm_client,
                auth_headers_system,
                entity_id=note_id,
                entity_type="note",
                entity_title=note_name,
                filename="empty.txt",
                content=b"",
                content_type="text/plain",
            )
