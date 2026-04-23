"""
Конкретные реализации tools.

Публичный список __all__ — источник имён для inline namespace (PythonNamespaceBuilder):
все перечисленные объекты попадают в eval по имени. Добавляя tool, включи имя в __all__.
"""

from .agent_session_tools import (
    ask_user,
    final_answer,
    finish,
    hitl_operator_task,
    reason,
    self_check,
)
from .docx_template import fill_docx_template
from .sandbox_codegen import sandbox_codegen
from .files import create_file, read_file
from .google_docs import (
    gdocs_append_text,
    gdocs_create_document,
    gdocs_delete_range,
    gdocs_find_replace,
    gdocs_insert_text,
    gdocs_read_document,
    gdocs_share_document,
)
from .lara_crm import (
    crm_analyze_note_text,
    crm_create_note,
    crm_create_note_and_analyze,
    crm_search_entities,
    flows_patch_flow,
    flows_patch_node,
    flows_read_context,
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
    "hitl_operator_task",
    "calculator",
    "crm_analyze_note_text",
    "crm_create_note",
    "crm_create_note_and_analyze",
    "crm_search_entities",
    "flows_patch_flow",
    "flows_patch_node",
    "flows_read_context",
    "cancel_scheduled_task",
    "create_file",
    "sandbox_codegen",
    "fill_docx_template",
    "final_answer",
    "gdocs_append_text",
    "gdocs_create_document",
    "gdocs_delete_range",
    "gdocs_find_replace",
    "gdocs_insert_text",
    "gdocs_read_document",
    "gdocs_share_document",
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
