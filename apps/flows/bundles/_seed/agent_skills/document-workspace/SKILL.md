---
name: document-workspace
description: Create, read, edit, open, rename/move/copy, and trash platform files and Office Documents (docx/xlsx/txt). Use when the user asks for reports, tables, file edits, or opening a document in the editor.
allowed-tools: read_file create_file documents_open_file documents_replace_text documents_append_text documents_update_cells documents_create_empty documents_rename documents_move documents_copy documents_delete documents_list_deleted documents_restore documents_permanent_delete format_text_markdown summarize_text
depends_on: docx-templates
---

# Document workspace

## Goal

Produce or edit platform files and keep them usable in Office Documents viewer; manage document lifecycle in catalogs.

## Procedure

1. If the user attached files — call `read_file` with names from `state.files`.
2. Blank Office document in a catalog — `documents_create_empty(title, document_type=word|cell|slide, catalog_id)`.
3. Create from content — `create_file` with correct extension; then `documents_open_file` with `catalog_id` when placement matters.
4. Edit known file:
   - text/docx: `documents_replace_text` or `documents_append_text`
   - spreadsheet cells: `documents_update_cells`
5. Rename / move / copy — `documents_rename` / `documents_move` / `documents_copy`.
6. Trash — `documents_delete` (soft); `documents_list_deleted`; `documents_restore` or `documents_permanent_delete`.
7. For cleaner prose — `format_text_markdown` / `summarize_text`.
8. Jinja2 Word templates — load `docx-templates` → `fill_docx_template`.

## Notes

- Always return `file_id` and editor/public link from tool results.
- Do not invent `file_id`; take it from tool results or `state.files`.
- Read reference `document-workspace-reference.md` for call examples.
- Catalog browse/ACL/RAG admin — skill `documents-catalog`.
