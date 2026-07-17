---
name: documents-platform
description: Office Documents service — catalogs, bindings, platform files, document editing, templates, visualizations, and company knowledge. Load from the Documents SPA or for document deliverables and indexed knowledge.
depends_on: document-workspace documents-catalog diagrams-viz knowledge-rag
---

# Documents service

## Goal

Choose the correct document workflow and preserve the distinction between Office catalog records, platform files, and indexed company knowledge. Knowledge lives under Documents (not a separate RAG SPA).

## Procedure

1. Use `catalog_id`, `binding_id`, `file_id` and `document_type` from UI context; never substitute one identifier for another.
2. Load child `documents-catalog` to browse catalogs, find documents (semantic/lexical), read content, or get an editor/preview link. The same tools are platform builtins for any Flows `llm_node`.
3. Load child `document-workspace` to create, open in editor, or mutate files (replace/append text, cells).
4. From `document-workspace`, load `docx-templates` for Jinja2 DOCX templates.
5. Load child `diagrams-viz` for `.viz` diagrams, charts and exports.
6. Load child `knowledge-rag` for company knowledge search, text ingest and namespace creation (`rag_search` / `rag_add_text` / `rag_create_namespace`). Prefer search before answering factual company questions.
7. For external sources, load `platform-workspace` then `web-research`.

## Capability boundary

Tools cover catalog browse/search/read/link, platform files, supported text/cell edits, templates, visualizations and knowledge search/ingest. Office catalog administration, binding ACL, public share rotate, trash and unsupported editor operations have no Lara operational tool; explain the Documents UI path without claiming a mutation.
