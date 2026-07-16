---
name: rag-platform
description: RAG service guidance for namespaces, indexed documents, ingestion, processing state, and grounded retrieval. Load from the RAG SPA or for company knowledge management.
depends_on: knowledge-rag
---

# RAG service

## Goal

Manage and use company knowledge while keeping platform files, indexed documents and vector namespaces distinct.

## Procedure

1. Inspect `namespace_id`, `document_id`, `file_id`, route and compact UI context.
2. Load child `knowledge-rag` for retrieval, text ingestion or namespace creation.
3. Search before answering company-specific factual questions and cite returned sources.
4. Ask for an explicit target before creating a namespace or adding text. Do not guess from a similarly named UI item.
5. Load root `documents-platform` when the task is about the source file itself rather than its indexed representation.

## Domain boundaries

- `file_id` identifies a platform file.
- `document_id` identifies a RAG index record.
- `namespace_id` identifies the technical vector namespace.
- Processing administration and file-to-index upload controls do not have additional Lara tools; guide the user through the current RAG UI when `knowledge-rag` does not cover the operation.
