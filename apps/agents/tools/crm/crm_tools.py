"""
CRM Tools - инструменты для AI ассистента.

Инструменты делают запросы к CRM API с контекстом текущего пользователя.
Используются агентом CRM Assistant для помощи пользователю.
"""

import logging
import os
from datetime import date, datetime
from typing import Optional, List, Dict, Any

from langchain_core.tools import tool
from pydantic import Field

from core.context import get_context
from core.http import get_httpx_client

logger = logging.getLogger(__name__)


def _get_crm_base_url() -> str:
    """
    Получает базовый URL CRM сервиса.
    
    Порядок приоритета:
    1. CRM_API_URL из переменной окружения
    2. crm_api_url из метаданных контекста
    3. Дефолтный localhost:8003
    """
    # Из переменной окружения
    env_url = os.environ.get("CRM_API_URL")
    if env_url:
        return env_url.rstrip("/")
    
    # Из контекста
    context = get_context()
    if context and context.metadata:
        ctx_url = context.metadata.get("crm_api_url")
        if ctx_url:
            return ctx_url.rstrip("/")
    
    # Дефолтный URL
    return "http://localhost:8003/crm/api/v1"


def _get_headers() -> Dict[str, str]:
    """Получает заголовки с контекстом пользователя"""
    headers = {"Content-Type": "application/json"}
    
    context = get_context()
    if context and context.active_company:
        headers["X-Company-Id"] = context.active_company.company_id
    if context and context.user:
        headers["X-User-Id"] = context.user.user_id
    if context and context.auth_token:
        headers["Authorization"] = f"Bearer {context.auth_token}"
    
    return headers


async def _crm_request(method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
    """Выполняет запрос к CRM API"""
    base_url = _get_crm_base_url()
    url = f"{base_url}{endpoint}"
    headers = _get_headers()
    
    async with get_httpx_client() as client:
        response = await client.request(
            method, 
            url, 
            headers=headers,
            timeout=30.0,
            **kwargs
        )
        
        if response.status_code == 404:
            return {"error": "Не найдено", "status": 404}
        
        response.raise_for_status()
        return response.json()


# === Notes Tools ===

@tool
async def search_notes(
    query: str = Field(description="Поисковый запрос по содержимому заметок"),
    limit: int = Field(default=10, description="Максимальное количество результатов")
) -> str:
    """
    Поиск заметок по тексту.
    Используй когда пользователь ищет информацию в своих заметках.
    """
    try:
        result = await _crm_request(
            "GET", 
            f"/notes/search?q={query}&limit={limit}"
        )
        
        if not result or (isinstance(result, list) and len(result) == 0):
            return f"По запросу '{query}' заметок не найдено."
        
        notes = result if isinstance(result, list) else result.get("items", [])
        
        output = f"Найдено {len(notes)} заметок по запросу '{query}':\n\n"
        for note in notes[:limit]:
            output += f"- **{note.get('title', 'Без названия')}** ({note.get('note_date', '')})\n"
            if note.get('ai_summary'):
                output += f"  Резюме: {note['ai_summary'][:100]}...\n"
            output += "\n"
        
        return output
    except Exception as e:
        logger.error(f"Ошибка поиска заметок: {e}")
        return f"Ошибка поиска: {str(e)}"


@tool
async def get_note_by_id(
    note_id: str = Field(description="ID заметки")
) -> str:
    """
    Получает полное содержимое заметки по ID.
    Используй когда нужно прочитать конкретную заметку.
    """
    try:
        note = await _crm_request("GET", f"/notes/{note_id}")
        
        if note.get("error"):
            return f"Заметка с ID {note_id} не найдена."
        
        output = f"## {note.get('title', 'Без названия')}\n\n"
        output += f"**Дата:** {note.get('note_date', 'не указана')}\n"
        output += f"**Тип:** {note.get('note_type', 'freeform')}\n\n"
        output += f"**Содержимое:**\n{note.get('content', '')}\n\n"
        
        if note.get('ai_summary'):
            output += f"**AI Резюме:** {note['ai_summary']}\n"
        
        if note.get('linked_entity_ids'):
            output += f"**Связанные сущности:** {len(note['linked_entity_ids'])} шт.\n"
        
        return output
    except Exception as e:
        logger.error(f"Ошибка получения заметки: {e}")
        return f"Ошибка: {str(e)}"


@tool
async def get_today_notes() -> str:
    """
    Получает заметки за сегодня.
    Используй для обзора дневной активности.
    """
    try:
        today = date.today().isoformat()
        result = await _crm_request("GET", f"/notes/daily/{today}")
        
        notes = result if isinstance(result, list) else result.get("items", [])
        
        if not notes:
            return "Сегодня заметок пока нет."
        
        output = f"## Заметки за сегодня ({today})\n\n"
        for note in notes:
            output += f"### {note.get('title', 'Без названия')}\n"
            content = note.get('content', '')[:200]
            output += f"{content}...\n\n"
        
        return output
    except Exception as e:
        logger.error(f"Ошибка получения заметок: {e}")
        return f"Ошибка: {str(e)}"


@tool
async def get_daily_summary(
    note_date: str = Field(description="Дата в формате YYYY-MM-DD")
) -> str:
    """
    Получает AI-саммари всех заметок за указанный день.
    Используй для быстрого обзора дня.
    """
    try:
        result = await _crm_request("GET", f"/notes/daily-summary/{note_date}")
        
        if isinstance(result, dict) and result.get("summary"):
            return f"## Саммари за {note_date}\n\n{result['summary']}"
        elif isinstance(result, str):
            return f"## Саммари за {note_date}\n\n{result}"
        else:
            return f"Нет данных для саммари за {note_date}"
    except Exception as e:
        logger.error(f"Ошибка получения саммари: {e}")
        return f"Ошибка: {str(e)}"


@tool
async def create_note(
    title: str,
    content: str,
    note_type: str = "freeform",
    status: str = "draft"
) -> str:
    """
    Создает новую заметку.
    Используй когда пользователь хочет записать информацию или создать черновик.
    По умолчанию создается черновик (draft) на сегодняшнюю дату.
    
    Args:
        title: Заголовок заметки
        content: Содержимое заметки в markdown
        note_type: Тип заметки - freeform, meeting_minutes или call_log
        status: Статус - draft (черновик) или published (опубликовано)
    """
    try:
        today = date.today().isoformat()
        
        payload = {
            "title": title,
            "content": content,
            "note_type": note_type,
            "note_date": today,
            "status": status,
        }
        
        result = await _crm_request("POST", "/notes", json=payload)
        
        if result.get("error"):
            return f"Ошибка создания заметки: {result.get('error')}"
        
        note_id = result.get("note_id", "")
        status_text = "черновик" if status == "draft" else "опубликована"
        
        return f"Заметка создана ({status_text}):\n- ID: {note_id}\n- Заголовок: {title}\n- Дата: {today}"
    except Exception as e:
        logger.error(f"Ошибка создания заметки: {e}")
        return f"Ошибка: {str(e)}"


# === Tasks Tools ===

@tool
async def search_tasks(
    status: Optional[str] = Field(default=None, description="Фильтр по статусу: pending, in_progress, completed, cancelled"),
    priority: Optional[str] = Field(default=None, description="Фильтр по приоритету: low, medium, high, urgent"),
    limit: int = Field(default=20, description="Максимальное количество задач")
) -> str:
    """
    Поиск задач с фильтрацией.
    Используй для просмотра задач по статусу или приоритету.
    """
    try:
        params = [f"limit={limit}"]
        if status:
            params.append(f"status={status}")
        if priority:
            params.append(f"priority={priority}")
        
        query = "&".join(params)
        result = await _crm_request("GET", f"/tasks?{query}")
        
        tasks = result if isinstance(result, list) else result.get("items", [])
        
        if not tasks:
            return "Задач не найдено."
        
        output = f"Найдено {len(tasks)} задач:\n\n"
        for task in tasks:
            priority_emoji = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(task.get('priority', 'medium'), "⚪")
            status_text = {"pending": "⏳", "in_progress": "🔄", "completed": "✅", "cancelled": "❌"}.get(task.get('status', 'pending'), "")
            
            output += f"{priority_emoji} {status_text} **{task.get('title', 'Без названия')}**\n"
            if task.get('due_date'):
                output += f"   Дедлайн: {task['due_date']}\n"
            if task.get('description'):
                output += f"   {task['description'][:100]}...\n"
            output += "\n"
        
        return output
    except Exception as e:
        logger.error(f"Ошибка поиска задач: {e}")
        return f"Ошибка: {str(e)}"


@tool
async def get_my_tasks(
    status: Optional[str] = Field(default="pending", description="Фильтр по статусу")
) -> str:
    """
    Получает мои текущие задачи.
    Используй для просмотра личных задач пользователя.
    """
    try:
        params = f"status={status}" if status else ""
        result = await _crm_request("GET", f"/tasks/my?{params}")
        
        tasks = result if isinstance(result, list) else result.get("items", [])
        
        if not tasks:
            return f"Нет задач со статусом '{status}'."
        
        output = f"## Мои задачи ({status})\n\n"
        for task in tasks:
            priority = task.get('priority', 'medium')
            output += f"- **{task.get('title')}** [{priority}]\n"
            if task.get('due_date'):
                output += f"  Дедлайн: {task['due_date']}\n"
        
        return output
    except Exception as e:
        logger.error(f"Ошибка получения задач: {e}")
        return f"Ошибка: {str(e)}"


@tool
async def get_overdue_tasks() -> str:
    """
    Получает просроченные задачи.
    Используй для напоминания о пропущенных дедлайнах.
    """
    try:
        result = await _crm_request("GET", "/tasks/overdue")
        
        tasks = result if isinstance(result, list) else result.get("items", [])
        
        if not tasks:
            return "Просроченных задач нет!"
        
        output = f"## ⚠️ Просроченные задачи ({len(tasks)})\n\n"
        for task in tasks:
            output += f"- **{task.get('title')}**\n"
            output += f"  Дедлайн был: {task.get('due_date')}\n"
            output += f"  Приоритет: {task.get('priority')}\n\n"
        
        return output
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return f"Ошибка: {str(e)}"


@tool
async def get_task_stats() -> str:
    """
    Получает статистику по задачам.
    Используй для обзора продуктивности.
    """
    try:
        result = await _crm_request("GET", "/tasks/stats")
        
        output = "## Статистика задач\n\n"
        output += f"- ⏳ Ожидают: {result.get('pending', 0)}\n"
        output += f"- 🔄 В работе: {result.get('in_progress', 0)}\n"
        output += f"- ✅ Завершено: {result.get('completed', 0)}\n"
        output += f"- ❌ Отменено: {result.get('cancelled', 0)}\n"
        
        return output
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return f"Ошибка: {str(e)}"


# === Entities Tools ===

@tool
async def search_entities(
    query: str = Field(description="Поисковый запрос (имя, название)"),
    entity_type: Optional[str] = Field(default=None, description="Тип сущности: person, organization, project"),
    limit: int = Field(default=10, description="Максимальное количество результатов")
) -> str:
    """
    Поиск сущностей (людей, организаций, проектов).
    Используй для поиска контактов или проектов.
    """
    try:
        params = [f"q={query}", f"limit={limit}"]
        if entity_type:
            params.append(f"type={entity_type}")
        
        result = await _crm_request("GET", f"/entities/search?{'&'.join(params)}")
        
        entities = result if isinstance(result, list) else result.get("items", [])
        
        if not entities:
            return f"По запросу '{query}' ничего не найдено."
        
        output = f"Найдено {len(entities)} сущностей:\n\n"
        for entity in entities:
            type_emoji = {"person": "👤", "organization": "🏢", "project": "📁"}.get(entity.get('entity_type', ''), "📌")
            output += f"{type_emoji} **{entity.get('name', 'Без имени')}** ({entity.get('entity_type', '')})\n"
            
            attrs = entity.get('attributes', {})
            if attrs.get('position'):
                output += f"   Должность: {attrs['position']}\n"
            if attrs.get('email'):
                output += f"   Email: {attrs['email']}\n"
            if attrs.get('phone'):
                output += f"   Телефон: {attrs['phone']}\n"
            output += "\n"
        
        return output
    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")
        return f"Ошибка: {str(e)}"


@tool
async def get_entity_by_id(
    entity_id: str = Field(description="ID сущности")
) -> str:
    """
    Получает подробную информацию о сущности.
    Используй для просмотра деталей контакта или проекта.
    """
    try:
        entity = await _crm_request("GET", f"/entities/{entity_id}")
        
        if entity.get("error"):
            return f"Сущность с ID {entity_id} не найдена."
        
        type_emoji = {"person": "👤", "organization": "🏢", "project": "📁"}.get(entity.get('entity_type', ''), "📌")
        output = f"## {type_emoji} {entity.get('name', 'Без имени')}\n\n"
        output += f"**Тип:** {entity.get('entity_type', 'неизвестно')}\n"
        output += f"**Статус:** {entity.get('status', 'active')}\n\n"
        
        attrs = entity.get('attributes', {})
        if attrs:
            output += "**Атрибуты:**\n"
            for key, value in attrs.items():
                output += f"- {key}: {value}\n"
        
        return output
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return f"Ошибка: {str(e)}"


@tool
async def get_entity_relationships(
    entity_id: str = Field(description="ID сущности"),
    depth: int = Field(default=1, description="Глубина связей (1-3)")
) -> str:
    """
    Получает связи сущности с другими сущностями.
    Используй для понимания контекста и окружения.
    """
    try:
        result = await _crm_request("GET", f"/graph/entity/{entity_id}?depth={depth}")
        
        nodes = result.get("nodes", [])
        edges = result.get("edges", [])
        
        if not nodes:
            return f"Связей для сущности {entity_id} не найдено."
        
        # Находим центральную сущность
        center = next((n for n in nodes if n.get("is_center")), nodes[0] if nodes else None)
        
        output = f"## Связи сущности: {center.get('label', 'Неизвестно') if center else entity_id}\n\n"
        output += f"Найдено {len(nodes) - 1} связанных сущностей:\n\n"
        
        for node in nodes:
            if node.get("is_center"):
                continue
            type_emoji = {"person": "👤", "organization": "🏢", "project": "📁"}.get(node.get('group', ''), "📌")
            output += f"{type_emoji} {node.get('label', 'Без имени')}\n"
        
        if edges:
            output += f"\n**Типы связей:** {len(edges)}\n"
            for edge in edges[:5]:
                output += f"- {edge.get('label', 'связь')}\n"
        
        return output
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return f"Ошибка: {str(e)}"

