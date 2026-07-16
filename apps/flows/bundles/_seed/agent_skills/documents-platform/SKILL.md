---
name: documents-platform
description: Office Documents service — catalogs, bindings, platform files, document editing, templates, and visualizations. Load from the Documents SPA or for document deliverables.
depends_on: document-workspace diagrams-viz
---

# Documents service

## Goal

Choose the correct document workflow and preserve the distinction between Office catalog records and platform files.

## Procedure

1. Use `catalog_id`, `binding_id`, `file_id` and `document_type` from UI context; never substitute one identifier for another.
2. Load child `document-workspace` to read, create, open or edit files.
3. From `document-workspace`, load `docx-templates` for Jinja2 DOCX templates.
4. Load child `diagrams-viz` for `.viz` diagrams, charts and exports.
5. For indexed company knowledge, load root `rag-platform`; for external sources, load `platform-workspace` then `web-research`.

## Capability boundary

Tools cover platform files, supported text/cell edits, templates and visualizations. Office catalog administration, binding changes, sharing policy and unsupported editor operations have no Lara operational tool; explain the Documents UI path without claiming a mutation.
