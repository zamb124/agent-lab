"""
End-to-end проверка финального LLM-сообщения для CRM analyze.

Тест поднимает реальный TaskIQ-worker, реальный flows-uvicorn и реальный
CRM (как остальные `real_taskiq` тесты), вызывает `/tasks/note-analyze` и
читает из Redis ровно те `messages`, которые получил MockLLM в `stream()`.
Затем проверяет, что:

1. В реальный rendered prompt уходит `EntityType.prompt` именно в той
   редакции, что лежит в БД на момент вызова (правка пользователя через
   CRM API подхватывается на следующем analyze).
2. В тот же prompt уходят `field.label`, `field.description` и
   enum-`values` — т.е. у каждой настроенной компанией формы поля
   действительно появляется описание для AI.
3. `RelationshipType.prompt`, отредактированный пользователем через
   репозиторий, тоже доходит до LLM.

Ни моков, ни monkeypatch: единственная инфраструктура — `MockLLM`,
который пишет получаемые `messages` в Redis (см. `core/clients/llm/mock.py`).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import cast

import pytest
from httpx import AsyncClient, Response

from apps.crm.container import CRMContainer
from apps.crm.system_templates import (
    NAMESPACE_TEMPLATE_SEEDS,
    NamespaceTemplateSeed,
    NamespaceTemplateTypeSpec,
)
from core.types import JsonObject
from tests.crm.e2e._json_helpers import json_object, object_dict, object_list, object_str

MockLlmRedisFactory = Callable[[list[object]], Awaitable[None]]
MockLlmCaptureFactory = Callable[[], Awaitable[list[JsonObject]]]

_META: dict[str, object] = {"dates_mentioned": [], "places_mentioned": [], "key_topics": []}


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _entity_id(response: Response) -> str:
    return object_str(_http_json(response).get("entity_id"), field="entity_id")


def _task_id(response: Response) -> str:
    return object_str(_http_json(response).get("task_id"), field="task_id")


def _seed_by_id(template_id: str) -> NamespaceTemplateSeed:
    for seed in NAMESPACE_TEMPLATE_SEEDS:
        if seed["template_id"] == template_id:
            return seed
    raise AssertionError(f"seed {template_id!r} not registered")


def _empty_analyze_response_for(note_title: str) -> dict[str, object]:
    """Возвращает пустой, но валидный по схеме analyze ответ — `note` есть, всё остальное пусто."""
    return {
        "type": "text",
        "content": json.dumps(
            {
                "note": {
                    "entity_type": "note",
                    "name": note_title,
                    "description": (
                        "Пустой захват: тест проверяет prompt, не содержимое ответа."
                    ),
                    "attributes": {},
                    "confidence": 0.5,
                },
                "entities": [],
                "relationships": [],
                "metadata": _META,
                "attachment_summaries": [],
            }
        ),
    }


def _analyze_mock_redis_queue(note_title: str) -> list[object]:
    """
    Два одинаковых ответа в очереди MockLLM: при полном прогоне с TaskIQ возможен лишний
    pop из mock_llm:responses до analyze; второй слот гарантирует валидный JSON для analyze.
    """
    one: object = _empty_analyze_response_for(note_title)
    return [one, one]


async def _create_namespace_from_template(
    crm_client: AsyncClient,
    auth_headers: dict[str, str],
    template_id: str,
    suffix: str,
) -> str:
    namespace_name = f"e2e_prompt_{template_id}_{suffix}"
    response = await crm_client.post(
        "/crm/api/v1/namespaces",
        json={
            "name": namespace_name,
            "description": f"e2e prompt-in-llm probe {template_id}",
            "template_id": template_id,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    return namespace_name


async def _wait_until_task_completes(
    crm_client: AsyncClient,
    headers: dict[str, str],
    task_id: str,
) -> dict[str, object]:
    deadline = time.monotonic() + 60.0
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        response = await crm_client.get(
            f"/crm/api/v1/tasks/{task_id}",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        last = _http_json(response)
        status = last.get("status")
        if status in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.4)
    assert last.get("status") == "completed", last
    return last


def _message_text(message: dict[str, object]) -> str:
    text = message.get("text")
    if isinstance(text, str) and text:
        return text
    chunks: list[str] = []
    for part_raw in object_list(message.get("parts")):
        if part_raw.get("type") == "text":
            part_text = part_raw.get("text")
            if isinstance(part_text, str):
                chunks.append(part_text)
    return "\n".join(chunks)


def _all_messages_text(call: dict[str, object]) -> str:
    """Склейка текстов всех сообщений вызова — для подстрочного поиска маркеров."""
    messages = object_list(call.get("messages"))
    chunks: list[str] = []
    for message in messages:
        message_text = _message_text(message)
        if message_text:
            chunks.append(message_text)
    return "\n\n".join(chunks)


def _call_matches_crm_analyze_schema(call: dict[str, object]) -> bool:
    """Матчит CRM analyze (structured output) по json_schema с полями note/entities/metadata/attachment_summaries.

    Предикат: не-structured вызовы (response_format отсутствует или не dict) не матчатся и не
    должны прерывать обход журнала MockLLM — поэтому проверки через isinstance, а не assert.
    """
    response_format = call.get("response_format")
    if not isinstance(response_format, dict):
        return False
    json_schema = response_format.get("json_schema")
    if not isinstance(json_schema, dict):
        return False
    schema = json_schema.get("schema")
    if not isinstance(schema, dict):
        return False
    required = schema.get("required")
    if isinstance(required, list):
        required_fields: set[str] = set()
        for required_item in cast(list[object], required):
            if isinstance(required_item, str):
                required_fields.add(required_item)
        if (
            "note" in required_fields
            and "entities" in required_fields
            and "attachment_summaries" in required_fields
            and "metadata" in required_fields
        ):
            return True
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return False
    return (
        "note" in properties
        and "entities" in properties
        and "attachment_summaries" in properties
        and "metadata" in properties
    )


def _matches_analyze_prompt(text: str) -> bool:
    if "# CRM Text Analyzer" in text or "CRM Text Analyzer" in text:
        return True
    if "ТИПЫ ENTITIES" in text and "ТИПЫ RELATIONSHIPS" in text:
        return True
    if "РАЗРЕШЁННЫЕ ИДЕНТИФИКАТОРЫ СУЩНОСТЕЙ" in text:
        return True
    return False


def _find_analyze_call(calls: list[JsonObject]) -> dict[str, object]:
    """Ищет в журнале вызов analyze: текст prompts/analyze.md или structured output CRM analyze."""
    for call in calls:
        call_object = object_dict(call, field="call")
        if _call_matches_crm_analyze_schema(call_object):
            return call_object
        if _matches_analyze_prompt(_all_messages_text(call_object)):
            return call_object
    first_call: object = calls[0] if calls else None
    raise AssertionError(
        "в журнале MockLLM нет analyze-вызова "
        + f"(всего вызовов: {len(calls)}); первая запись: {first_call!r}"
    )


def _ticket_type_spec(seed: NamespaceTemplateSeed) -> NamespaceTemplateTypeSpec:
    for type_spec in seed["types"]:
        if type_spec.get("type_id") == "ticket":
            return type_spec
    raise AssertionError("support seed must contain ticket type")


@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
class TestTemplatePromptReachesLLM:
    """Конфигурация шаблона/правки компании уходит в реальный LLM call."""

    @pytest.mark.asyncio
    async def test_user_edited_entity_type_prompt_reaches_llm(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        mock_llm_capture: MockLlmCaptureFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        ns_name = await _create_namespace_from_template(
            crm_client, auth_headers_system, "marketing", unique_id
        )

        marker = f"CAMPAIGN-LLM-MARKER-{unique_id}"
        new_prompt = (
            f"{marker}\nИзвлекай только performance-кампании с подтверждённым "
            "бюджетом > 0 и валютой. Игнорируй brand-awareness без бюджета."
        )
        update_resp = await crm_client.put(
            "/crm/api/v1/entity-types/campaign",
            params={"namespace": ns_name},
            json={"prompt": new_prompt},
            headers=auth_headers_system,
        )
        assert update_resp.status_code == 200, update_resp.text

        note_title = f"Кампания probe {unique_id}"
        await mock_llm_redis(_analyze_mock_redis_queue(note_title))

        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": note_title,
                "description": (
                    "Запускаем performance-кампанию Q4 на $30k, "
                    "до конца октября, цель — лиды."
                ),
                "namespace": ns_name,
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code == 200, note_resp.text
        note_id = _entity_id(note_resp)

        start = await crm_client.post(
            "/crm/api/v1/tasks/note-analyze",
            json={
                "note_id": note_id,
                "check_duplicates": False,
                "include_attachments": False,
            },
            headers=auth_headers_system,
        )
        assert start.status_code == 202, start.text
        _ = await _wait_until_task_completes(
            crm_client, auth_headers_system, _task_id(start)
        )

        calls = await mock_llm_capture()
        analyze_call = _find_analyze_call(calls)
        prompt_text = _all_messages_text(analyze_call)
        assert marker in prompt_text, (
            "обновлённый EntityType.prompt должен попадать в финальный rendered prompt analyze"
        )
        assert "Извлекай только performance-кампании" in prompt_text

    @pytest.mark.asyncio
    async def test_user_edited_field_label_and_enum_values_reach_llm(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        mock_llm_capture: MockLlmCaptureFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        ns_name = await _create_namespace_from_template(
            crm_client, auth_headers_system, "support", unique_id
        )

        unique_label = f"Серьёзность инцидента {unique_id}"
        unique_description = f"Внутренняя классификация SEV (метка теста {unique_id})"
        unique_value_id = f"sev_test_{unique_id}".replace("-", "_")
        update_resp = await crm_client.put(
            "/crm/api/v1/entity-types/ticket",
            params={"namespace": ns_name},
            json={
                "optional_fields": {
                    "severity": {
                        "type": "enum",
                        "label": unique_label,
                        "description": unique_description,
                        "values": [unique_value_id, "sev1", "sev2"],
                    },
                },
            },
            headers=auth_headers_system,
        )
        assert update_resp.status_code == 200, update_resp.text

        note_title = f"Тикет probe {unique_id}"
        await mock_llm_redis(_analyze_mock_redis_queue(note_title))

        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": note_title,
                "description": (
                    "Прилетел инцидент: бэкенд CRM не отдаёт список заметок, "
                    "клиент в проде, severity sev1."
                ),
                "namespace": ns_name,
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code == 200, note_resp.text
        note_id = _entity_id(note_resp)

        start = await crm_client.post(
            "/crm/api/v1/tasks/note-analyze",
            json={
                "note_id": note_id,
                "check_duplicates": False,
                "include_attachments": False,
            },
            headers=auth_headers_system,
        )
        assert start.status_code == 202, start.text
        _ = await _wait_until_task_completes(
            crm_client, auth_headers_system, _task_id(start)
        )

        calls = await mock_llm_capture()
        analyze_call = _find_analyze_call(calls)
        prompt_text = _all_messages_text(analyze_call)

        assert unique_label in prompt_text, (
            "label поля из БД должен попасть в rendered prompt analyze"
        )
        assert unique_description in prompt_text, (
            "description поля из БД должен попасть в rendered prompt analyze"
        )
        assert unique_value_id in prompt_text, (
            "значение enum-поля из БД должно попасть в rendered prompt analyze"
        )

    @pytest.mark.asyncio
    async def test_user_edited_relationship_type_prompt_reaches_llm(
        self,
        crm_client: AsyncClient,
        crm_container: CRMContainer,
        mock_llm_redis: MockLlmRedisFactory,
        mock_llm_capture: MockLlmCaptureFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """
        Прямая правка системного `RelationshipType.prompt` через репозиторий
        (как это делает любое UI/SDK, общающееся с БД компании) тоже уходит
        в финальный analyze prompt.
        """
        ns_name = await _create_namespace_from_template(
            crm_client, auth_headers_system, "sales", unique_id
        )

        marker = f"REL-LLM-MARKER-{unique_id}"
        new_prompt = (
            f"{marker}\nКОГДА ИСПОЛЬЗОВАТЬ: только для явного «упомянул». "
            "ПРИМЕР: «Иван упомянул проект X» → mentions от note к проекту. "
            "КОГДА НЕ ИСПОЛЬЗОВАТЬ: для блокировок и владения."
        )

        repo = crm_container.relationship_type_repository
        all_types = await repo.list_by_company(include_system=True, limit=1000)
        mentions_row = next((row for row in all_types if row.type_id == "mentions"), None)
        assert mentions_row is not None, "у компании system должен быть тип mentions"
        original_prompt = mentions_row.prompt
        try:
            mentions_row.prompt = new_prompt
            _ = await repo.update(mentions_row)

            note_title = f"Звонок probe {unique_id}"
            await mock_llm_redis(_analyze_mock_redis_queue(note_title))

            note_resp = await crm_client.post(
                "/crm/api/v1/entities/",
                json={
                    "entity_type": "note",
                    "name": note_title,
                    "description": (
                        "Звонок с клиентом: упомянули проект Альфа и сделку Q4."
                    ),
                    "namespace": ns_name,
                },
                headers=auth_headers_system,
            )
            assert note_resp.status_code == 200, note_resp.text
            note_id = _entity_id(note_resp)

            start = await crm_client.post(
                "/crm/api/v1/tasks/note-analyze",
                json={
                    "note_id": note_id,
                    "check_duplicates": False,
                    "include_attachments": False,
                },
                headers=auth_headers_system,
            )
            assert start.status_code == 202, start.text
            _ = await _wait_until_task_completes(
                crm_client, auth_headers_system, _task_id(start)
            )

            calls = await mock_llm_capture()
            analyze_call = _find_analyze_call(calls)
            prompt_text = _all_messages_text(analyze_call)
            assert marker in prompt_text, (
                "правка relationship.prompt должна попадать в rendered analyze prompt"
            )
        finally:
            mentions_row.prompt = original_prompt
            _ = await repo.update(mentions_row)

    @pytest.mark.asyncio
    async def test_seed_specific_type_prompt_visible_in_llm_for_that_namespace(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        mock_llm_capture: MockLlmCaptureFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """
        Без правок: prompt из шаблона `support` (например `ticket`) уходит
        в LLM ровно в формулировке seed'а — никакой подмены.
        """
        seed = _seed_by_id("support")
        ticket_spec = _ticket_type_spec(seed)
        prompt_raw = ticket_spec.get("prompt")
        assert isinstance(prompt_raw, str) and prompt_raw, "для тикета в support seed обязан быть prompt"
        prompt_marker = prompt_raw.splitlines()[0].strip()
        assert prompt_marker, "у seed prompt-а должна быть непустая первая строка"

        ns_name = await _create_namespace_from_template(
            crm_client, auth_headers_system, "support", unique_id
        )

        note_title = f"Тикет seed-prompt probe {unique_id}"
        await mock_llm_redis(_analyze_mock_redis_queue(note_title))

        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": note_title,
                "description": (
                    "Клиент репортит баг: при загрузке отчётов 500. "
                    "Срочный тикет, sev1."
                ),
                "namespace": ns_name,
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code == 200, note_resp.text
        note_id = _entity_id(note_resp)

        start = await crm_client.post(
            "/crm/api/v1/tasks/note-analyze",
            json={
                "note_id": note_id,
                "check_duplicates": False,
                "include_attachments": False,
            },
            headers=auth_headers_system,
        )
        assert start.status_code == 202, start.text
        _ = await _wait_until_task_completes(
            crm_client, auth_headers_system, _task_id(start)
        )

        calls = await mock_llm_capture()
        analyze_call = _find_analyze_call(calls)
        prompt_text = _all_messages_text(analyze_call)
        assert prompt_marker in prompt_text, (
            "prompt из seed support/ticket должен попадать в rendered analyze prompt; "
            + f"искали маркер: {prompt_marker!r}"
        )
