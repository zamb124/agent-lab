from __future__ import annotations

from pathlib import Path

from core.types import JsonObject, parse_json_object, require_json_object


def test_simple_crawler_bundle_function_first_contract() -> None:
    bundle_path = Path("apps/flows/bundles/simple_crawler/flow.json")
    payload = parse_json_object(bundle_path.read_text(encoding="utf-8"), str(bundle_path))

    assert payload.get("entry") == "bootstrap_session"

    nodes = require_json_object(payload.get("nodes"), "simple_crawler.nodes")
    llm_nodes: list[str] = []
    for node_id, raw_node in nodes.items():
        if not isinstance(raw_node, dict):
            continue
        node = require_json_object(raw_node, f"simple_crawler.nodes.{node_id}")
        if node.get("type") == "llm_node":
            llm_nodes.append(node_id)
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

    crawler = require_json_object(nodes.get("crawler_answer"), "simple_crawler.nodes.crawler_answer")
    assert crawler.get("type") == "llm_node"
    tools = crawler.get("tools")
    assert isinstance(tools, list) and any(
        isinstance(t, dict)
        and require_json_object(t, "simple_crawler.crawler_answer.tool").get("tool_id")
        == "simple_crawler_rag_search"
        for t in tools
    )

    variables: JsonObject = require_json_object(payload.get("variables"), "simple_crawler.variables")
    assert variables.get("crawl_pages_limit") == 5
    assert variables.get("search_queries_count") == 3
    assert variables.get("search_links_per_query") == 5
    assert variables.get("rag_embedding_provider") == "provider_litserve"
    assert variables.get("rag_embedding_model") == "qwen/qwen3-embedding-0.6b"
    assert variables.get("rag_embedding_dimension") == 1024
