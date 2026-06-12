"""Спеки импорта builtin tools для runtime registries."""

from __future__ import annotations

import importlib
from functools import lru_cache

from apps.flows.src.tools.base import BaseTool

BUILTIN_TOOL_SPECS: tuple[tuple[str, str], ...] = (
    ("apps.flows.tools.math_tools", "calculator"),
    ("apps.flows.tools.files", "create_file"),
    ("apps.flows.tools.documents", "documents_open_file"),
    ("apps.flows.tools.documents", "documents_replace_text"),
    ("apps.flows.tools.documents", "documents_append_text"),
    ("apps.flows.tools.documents", "documents_update_cells"),
    ("apps.flows.tools.sandbox_codegen", "sandbox_codegen"),
    ("apps.flows.tools.google_docs", "gdocs_append_text"),
    ("apps.flows.tools.google_docs", "gdocs_create_document"),
    ("apps.flows.tools.google_docs", "gdocs_delete_range"),
    ("apps.flows.tools.google_docs", "gdocs_find_replace"),
    ("apps.flows.tools.google_docs", "gdocs_insert_text"),
    ("apps.flows.tools.google_docs", "gdocs_read_document"),
    ("apps.flows.tools.google_docs", "gdocs_share_document"),
    ("apps.flows.tools.format_text_markdown", "format_text_markdown"),
    ("apps.flows.tools.pravo", "pravo_catalog_search"),
    ("apps.flows.tools.pravo", "pravo_document_rag_search"),
    ("apps.flows.tools.rag", "rag_add_text"),
    ("apps.flows.tools.rag", "rag_create_namespace"),
    ("apps.flows.tools.rag", "rag_search"),
    ("apps.flows.tools.index_search", "index_search"),
    ("apps.flows.tools.index_search", "runet_search"),
    ("apps.flows.tools.documentation", "docs_search"),
    ("apps.flows.tools.documentation", "docs_prepare_context"),
    ("apps.flows.tools.lara_crm", "crm_analyze_note_text"),
    ("apps.flows.tools.lara_crm", "crm_create_entity"),
    ("apps.flows.tools.lara_crm", "crm_create_note"),
    ("apps.flows.tools.lara_crm", "crm_create_note_and_analyze"),
    ("apps.flows.tools.lara_crm", "crm_create_relationship"),
    ("apps.flows.tools.lara_crm", "crm_daily_summary"),
    ("apps.flows.tools.lara_crm", "crm_get_entity"),
    ("apps.flows.tools.lara_crm", "crm_list_entity_types"),
    ("apps.flows.tools.lara_crm", "crm_search_entities"),
    ("apps.flows.tools.lara_crm", "flows_read_context"),
    ("apps.flows.tools.lara_crm", "flows_patch_node"),
    ("apps.flows.tools.lara_crm", "flows_patch_flow"),
    ("apps.flows.tools.docx_template", "fill_docx_template"),
    ("apps.flows.tools.agent_session_tools", "final_answer"),
    ("apps.flows.tools.finish_tool", "finish"),
    ("apps.flows.tools.lara_crm", "push_embed_blocks"),
    ("apps.flows.tools.files", "read_file"),
    ("apps.flows.tools.agent_session_tools", "reason"),
    ("apps.flows.tools.agent_session_tools", "ask_user"),
    ("apps.flows.tools.summarize_text", "summarize_text"),
    ("apps.flows.tools.agent_session_tools", "hitl_operator_task"),
    ("apps.flows.tools.scheduling", "schedule_cron_task"),
    ("apps.flows.tools.scheduling", "schedule_interval_task"),
    ("apps.flows.tools.scheduling", "schedule_one_time_task"),
    ("apps.flows.tools.scheduling", "list_scheduled_tasks"),
    ("apps.flows.tools.scheduling", "cancel_scheduled_task"),
    ("apps.flows.tools.web_browser", "browser_duckduckgo_links"),
    ("apps.flows.tools.web_browser", "browser_duckduckgo_links_batch"),
    ("apps.flows.tools.web_browser", "browser_page_markdown"),
    ("apps.flows.tools.web_browser", "browser_page_snapshot"),
)


@lru_cache(maxsize=1)
def builtin_tool_ids() -> frozenset[str]:
    """Возвращает канонические id, зарезервированные для доверенных platform tools."""
    ids: list[str] = []
    for module_name, attr_name in BUILTIN_TOOL_SPECS:
        module = importlib.import_module(module_name)
        raw_tool = module.__dict__.get(attr_name)
        if not isinstance(raw_tool, BaseTool):
            raise TypeError(
                f"Builtin tool {module_name}.{attr_name} must be a BaseTool instance"
            )
        ids.append(raw_tool.name if raw_tool.name else attr_name)
    return frozenset(ids)


__all__ = ["BUILTIN_TOOL_SPECS", "builtin_tool_ids"]
