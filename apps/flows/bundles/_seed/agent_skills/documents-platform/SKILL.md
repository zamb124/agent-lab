---
name: documents-platform
description: Office Documents service — catalogs, documents, platform files, document editing, templates, visualizations, and company knowledge. Load from the Documents SPA or for document deliverables and indexed knowledge.
depends_on: document-workspace documents-catalog diagrams-viz knowledge-rag team-directory
---

# Documents service

## Goal

Choose the correct document workflow and preserve the distinction between Office catalog records, platform files, and indexed company knowledge. Knowledge lives under Documents (not a separate RAG SPA).

## Procedure

1. Use `catalog_id`, `file_id` and `document_type` from UI context; never substitute one identifier for another.
2. Load child `documents-catalog` to browse/find/read, manage folders/members/ACL/public links, and catalog RAG index admin.
3. Load child `document-workspace` to create (empty or `create_file`), open, mutate, rename/move/copy, and trash.
4. From `document-workspace`, load `docx-templates` for Jinja2 DOCX templates.
5. Load child `diagrams-viz` for `.viz` diagrams, charts and exports.
6. Load child `knowledge-rag` for company knowledge search/ingest (`rag_*`) — not the same as catalog RAG admin.
7. Load `team-directory` before adding catalog members (`team_resolve_user`).
8. For external sources, load `platform-workspace` then `web-research`.
9. Read reference `documents-employee-methodology.md` for intent→tool chains.

## Capability boundary

Tools cover catalog browse/admin, search/read/link, lifecycle (empty/rename/move/copy/trash), ACL/public link rotate, catalog RAG enable/rebuild, platform files, text/cell edits, templates, visualizations and knowledge search/ingest.

OnlyOffice editor UI, Document Server JWT/callback/anonymous viewer, starred/recent UI prefs and full rich OO formatting (slides/images beyond server mutations) have no Lara operational tool — explain the Documents UI path without claiming a mutation.
