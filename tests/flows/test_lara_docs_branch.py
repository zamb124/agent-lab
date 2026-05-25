import json
from pathlib import Path

from apps.flows.tools.builtin_specs import builtin_tool_ids


def test_lara_docs_branch_prefetches_docs_without_llm_tools():
    flow = json.loads(Path("apps/flows/bundles/lara/flow.json").read_text())
    docs_branch = flow["branches"]["docs"]
    assert docs_branch["entry"] == "docs_lookup"
    assert docs_branch["nodes"]["main"]["tools"] == []
    assert {"from_node": "docs_lookup", "to_node": "main"} in docs_branch["edges"]
    lookup_code = docs_branch["nodes"]["docs_lookup"]["code"]
    compile(lookup_code, "lara_docs_lookup", "exec")
    assert "tools.docs_prepare_context" in lookup_code
    assert "tools.call_builtin" not in lookup_code


def test_docs_prepare_context_is_registered_as_builtin_tool():
    assert "docs_prepare_context" in builtin_tool_ids()
