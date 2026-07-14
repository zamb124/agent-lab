---
name: docx-templates
description: Fill Word (.docx) Jinja2 templates from state.files. Use after document-workspace when the user has a .docx template with placeholders.
allowed-tools: fill_docx_template
activation: explicit
---

# DOCX templates

## Goal

Fill a `.docx` template (docxtpl / Jinja2) attached in `state.files` and return a new filled file.

## Procedure

1. Load only after `document-workspace` (this skill is its depends_on child).
2. Confirm a `.docx` template is in `state.files` (user attachment or prior download).
3. Call `fill_docx_template` with:
   - `context` — mapping of placeholder values
   - `output_original_name` — result name ending with `.docx`
   - optional `file_name` — template `original_name` if several docx files exist
4. Return the new file to the user; open via `documents_open_file` if they want to edit further.

## Notes

- Template must use Jinja2 markers (`{{ var }}`, `{% for %}`, filters).
- Empty `state.files` → ask the user to attach the template first.
