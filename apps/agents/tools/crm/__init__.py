"""
CRM Tools - инструменты для работы с CRM системой.

Эти инструменты позволяют AI ассистенту:
- Искать и просматривать заметки
- Управлять задачами
- Находить сущности (люди, организации, проекты)
- Анализировать связи в графе
"""

from apps.agents.tools.crm.crm_tools import (
    search_notes,
    get_note_by_id,
    get_today_notes,
    create_note,
    search_tasks,
    get_my_tasks,
    get_overdue_tasks,
    search_entities,
    get_entity_by_id,
    get_entity_relationships,
    get_daily_summary,
    get_task_stats,
)

__all__ = [
    "search_notes",
    "get_note_by_id",
    "get_today_notes",
    "create_note",
    "search_tasks",
    "get_my_tasks",
    "get_overdue_tasks",
    "search_entities",
    "get_entity_by_id",
    "get_entity_relationships",
    "get_daily_summary",
    "get_task_stats",
]

