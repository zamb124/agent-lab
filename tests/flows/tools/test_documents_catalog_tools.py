"""Registry contract for Documents catalog builtins (no IO)."""

from __future__ import annotations

from apps.flows.tools.builtin_specs import BUILTIN_TOOL_SPECS, builtin_tool_ids
from apps.flows.tools.documents.documents_catalog import (
    documents_find,
    documents_get_link,
    documents_list_catalog,
    documents_read,
)

_CATALOG_TOOL_IDS = (
    "documents_list_catalog",
    "documents_find",
    "documents_read",
    "documents_get_link",
)
_EXPECTED_TAGS = {"documents"}


def test_documents_catalog_builtins_registered_with_tags() -> None:
    registered = builtin_tool_ids()
    for tool_id in _CATALOG_TOOL_IDS:
        assert tool_id in registered
    for tool in (
        documents_list_catalog,
        documents_find,
        documents_read,
        documents_get_link,
    ):
        assert set(tool.tags) == _EXPECTED_TAGS
    spec_names = {attr for _module, attr in BUILTIN_TOOL_SPECS}
    assert set(_CATALOG_TOOL_IDS).issubset(spec_names)
