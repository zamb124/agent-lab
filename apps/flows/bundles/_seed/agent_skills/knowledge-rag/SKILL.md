---
name: knowledge-rag
description: Search and write company RAG knowledge and platform documentation. Use when the user asks about internal knowledge, docs portal, or storing text in a vector namespace.
allowed-tools: rag_search rag_add_text rag_create_namespace docs_search docs_prepare_context
---

# Knowledge and RAG

## Goal

Retrieve grounded answers from company RAG / platform docs, and optionally ingest new text.

## Procedure

1. Platform product docs — `docs_search`, then `docs_prepare_context` for a packed context block.
2. Company knowledge — `rag_search` with the active namespace (ask user if unclear).
3. To add material — `rag_create_namespace` only if a new namespace is required, then `rag_add_text`.
4. Cite sources from tool results; do not invent document ids.

## Notes

- Prefer search before answering factual company questions.
- Keep ingested text scoped to the namespace the user approved.
