"""
Конкретные реализации tools.

Публичный список __all__ — источник имён для inline namespace (PythonNamespaceBuilder):
все перечисленные объекты попадают в eval по имени. Добавляя tool, включи имя в __all__.
"""

from .agent_session_tools import ask_user, final_answer, finish, reason, self_check
from .docx_template import fill_docx_template
from .files import create_file, read_file
from .lara_crm import (
    crm_analyze_note_text,
    crm_create_note,
    crm_create_note_and_analyze,
    crm_search_entities,
    push_embed_blocks,
)
from .math_tools import calculator
from .rag import rag_add_text, rag_create_namespace, rag_search
from .scheduling import (
    cancel_scheduled_task,
    list_scheduled_tasks,
    schedule_cron_task,
    schedule_interval_task,
    schedule_one_time_task,
)

__all__ = [
    "ask_user",
    "calculator",
    "crm_analyze_note_text",
    "crm_create_note",
    "crm_create_note_and_analyze",
    "crm_search_entities",
    "cancel_scheduled_task",
    "create_file",
    "fill_docx_template",
    "final_answer",
    "finish",
    "list_scheduled_tasks",
    "push_embed_blocks",
    "rag_add_text",
    "rag_create_namespace",
    "rag_search",
    "read_file",
    "reason",
    "self_check",
    "schedule_cron_task",
    "schedule_interval_task",
    "schedule_one_time_task",
]
