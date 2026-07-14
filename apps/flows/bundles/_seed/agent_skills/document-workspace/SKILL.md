---
name: document-workspace
description: Create, read, edit, and open platform files and Office Documents (docx/xlsx/txt). Use when the user asks for reports, tables, file edits, or opening a document in the editor.
allowed-tools: read_file create_file documents_open_file documents_replace_text documents_append_text documents_update_cells format_text_markdown summarize_text
depends_on: docx-templates
---

# Document workspace

## Goal

Produce or edit platform files and keep them usable in Office Documents viewer.

## Procedure

1. If the user attached files — call `read_file` with names from `state.files`.
2. To create a new deliverable — `create_file` with correct extension (`.md`, `.docx`, `.xlsx`, `.pdf`, `.html`, `.csv`, `.txt`). Prefer `content_mode=markdown` for rich docs.
3. To open a file in Documents UI — `documents_open_file` with `file_id` or `file_name`.
4. To edit an already opened/known file:
   - text/docx: `documents_replace_text` or `documents_append_text`
   - spreadsheet cells: `documents_update_cells`
5. For cleaner prose before writing — `format_text_markdown` / `summarize_text`.
6. For Jinja2 Word templates after the file is in `state.files` — load skill `docx-templates` (listed in depends_on) and call `fill_docx_template`.

## Notes

- Always return the resulting file link / `file_id` to the user.
- Do not invent `file_id`; take it from tool results or `state.files`.
- Read reference `document-workspace-reference.md` for call examples.
