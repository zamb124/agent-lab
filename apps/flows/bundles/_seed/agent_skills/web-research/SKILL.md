---
name: web-research
description: Web and platform index search plus bounded browser page snapshots. Use for external facts, multi-query research, reading public pages, or preserving a page artifact.
allowed-tools: web_search index_search browser_duckduckgo_links browser_duckduckgo_links_batch browser_page_markdown browser_page_snapshot
---

# Web research

## Goal

Find and summarize external information with explicit sources.

## Procedure

1. Broad discovery — `web_search` and/or `index_search`.
2. One DuckDuckGo formulation — `browser_duckduckgo_links`.
3. Several complementary formulations — `browser_duckduckgo_links_batch`; use it instead of serial searches and deduplicate by the returned URL order.
4. Read a specific URL without retaining an artifact — `browser_page_markdown`.
5. Read and retain the page as a platform artifact — `browser_page_snapshot`; use the returned `file_id` rather than inventing one.
6. Summarize with direct links and distinguish quoted page facts from your synthesis.

## Notes

- Do not claim live access beyond tool results.
- Prefer primary sources over secondary summaries when available.
- Respect bounded/truncated page text and say when the relevant section may be outside the returned snapshot.
- Do not use a snapshot for authenticated or secret-bearing pages.
