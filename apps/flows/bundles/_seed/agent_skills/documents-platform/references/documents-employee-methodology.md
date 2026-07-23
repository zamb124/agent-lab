# Documents employee methodology

## Context first

Prefer IDs from Documents UI / Lara context:

1. `catalog_id` — active folder.
2. `file_id` — selected document (never invent; never swap with `catalog_id`).
3. `document_type` — OnlyOffice kind when present (`word`/`cell`/`slide`).

Namespace comes from session (`X-Platform-Namespace`); tools fail closed if missing.

## Scenario matrix

| Intent | Chain |
|---|---|
| What folders do I have? | `documents_list_catalog` (no catalog_id) |
| Browse folder | `documents_list_catalog(catalog_id=…)` |
| Find by meaning/title | `documents_find(query, catalog_id?, mode=auto\|semantic\|lexical)` |
| Read content | `documents_read(file_id=…)` |
| SPA editor/preview URL | `documents_get_link` — **not** a public internet share |
| Blank Office doc in catalog | `documents_create_empty(title, document_type, catalog_id)` |
| Create from text/markdown | `create_file` → `documents_open_file(catalog_id=…)` |
| Edit text/cells | `documents_replace_text` / `append_text` / `update_cells` |
| Rename / move / copy | `documents_rename` / `documents_move` / `documents_copy` |
| Trash | `documents_delete` → `documents_list_deleted` → `documents_restore` or `documents_permanent_delete` |
| New folder | `documents_create_catalog` (+ optional `parent_catalog_id`) |
| Members | `documents_list_catalog_members` → `team_resolve_user` → `documents_add_catalog_member` |
| Company/members/link ACL | `documents_get_access` → `documents_patch_access` |
| Public share URL | `documents_patch_access(link_enabled=true)` then `documents_rotate_public_link` |
| Catalog semantic index | `documents_catalog_rag_status` → `enable` / `rebuild`; then `documents_find(mode=semantic)` |
| Company knowledge (not catalog RAG) | load `knowledge-rag` (`rag_search` / `rag_add_text`) |
| Diagrams | load `diagrams-viz` |
| DOCX template fill | load `docx-templates` |

## empty vs create_file

- **`documents_create_empty`** — canonical blank OOXML/csv in a catalog (`word`/`cell`/`slide`).
- **`create_file`** — platform file from content (md/docx/xlsx/…); bind with `documents_open_file`.

## Boundaries

- OnlyOffice iframe, editor-config JWT, Document Server callback/download, anonymous viewer — UI/infra only.
- Starred/recent explorer prefs — UI only.
- Do not claim public share from `documents_get_link`.
- Do not invent `file_id` / `catalog_id` / `user_id`.
