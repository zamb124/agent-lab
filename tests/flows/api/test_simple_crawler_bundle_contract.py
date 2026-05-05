from __future__ import annotations

import json
from pathlib import Path


def test_simple_crawler_bundle_function_first_contract() -> None:
    bundle_path = Path("apps/flows/bundles/simple_crawler/flow.json")
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))

    assert payload.get("entry") == "bootstrap_session"

    nodes = payload["nodes"]
    llm_nodes = [node_id for node_id, cfg in nodes.items() if cfg.get("type") == "llm_node"]
    assert sorted(llm_nodes) == ["crawler_answer", "plan_queries"]

    required_code_nodes = {
        "bootstrap_session",
        "prepare_inputs",
        "ensure_rag_namespace",
        "check_rag_context",
        "search_duckduckgo_batch",
        "fetch_pages_markdown",
        "rag_ingest_markdown_batch",
    }
    assert required_code_nodes.issubset(set(nodes.keys()))
    assert "merge_search_results_30" not in nodes

    crawler = nodes["crawler_answer"]
    assert crawler.get("type") == "llm_node"
    tools = crawler.get("tools")
    assert isinstance(tools, list) and any(
        isinstance(t, dict) and t.get("tool_id") == "simple_crawler_rag_search" for t in tools
    )

    variables = payload.get("variables", {})
    assert variables.get("crawl_pages_limit") == 5
    assert variables.get("search_queries_count") == 3
    assert variables.get("search_links_per_query") == 5
    assert variables.get("rag_embedding_provider") == "provider_litserve"
    assert variables.get("rag_embedding_model") == "qwen/qwen3-embedding-8b"
    assert variables.get("rag_embedding_dimension") == 4096
