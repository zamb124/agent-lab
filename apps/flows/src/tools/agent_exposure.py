"""Курируемая экспозиция builtin tools для HumanitecAgent Platform MCP."""

from typing import Final

DEFAULT_AGENT_TOOL_IDS: Final[frozenset[str]] = frozenset(
    {
        "rag_search",
        "index_search",
        "runet_search",
        "read_file",
        "crm_search_entities",
        "crm_get_entity",
        "docs_search",
        "browser_duckduckgo_links",
        "browser_page_markdown",
    }
)
