---
name: documents-catalog
description: Browse, search, read and link Documents library catalogs and bindings. Platform builtins for Flows llm_node and Lara — tags documents/office/catalog.
allowed-tools: documents_list_catalog documents_find documents_read documents_get_link
---

# Documents catalog

## Goal

Navigate the Documents library (catalogs + bindings) without inventing ids. These tools are platform builtins: attach them on any `llm_node.tools` in Flows, or unlock via this skill.

## Procedure

1. Browse — `documents_list_catalog` without `catalog_id` for root catalogs; with `catalog_id` for child catalogs + documents in that folder (non-recursive).
2. Find — `documents_find(query, catalog_id?, mode=auto|semantic|lexical)`. Prefer `auto`: semantic when the catalog has RAG index enabled, otherwise lexical title search. If explicit `semantic` fails with `rag_index_disabled`, retry with `lexical` or `auto`.
3. Read content — `documents_read(binding_id|file_id, page_start, page_end)` via FileReader pagination.
4. Share path — `documents_get_link(binding_id, kind=editor|preview)` for a UI URL. Do not claim a public internet share was created.

## Rules

- Never invent `catalog_id`, `binding_id` or `file_id`.
- Mutations (create/edit file, replace text, templates, viz) — load skill `document-workspace` (or attach those tools on the node).
- Catalog admin, members, public link rotate, trash — no tools here; explain the Documents UI path.

## Cross-domain

Company vector knowledge ingest outside a catalog index — skill `knowledge-rag`. External web — `web-research`.
